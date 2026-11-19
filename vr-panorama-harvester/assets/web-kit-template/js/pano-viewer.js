/*!
 * PanoViewer —— 零依赖的等距柱状全景查看器（WebGL1/2）
 * 不依赖 three.js，单文件约 60KB，可离线运行。
 * 用法：const v = new PanoViewer(el); v.load('xx.webp'); v.setHotspots([{lon:30,lat:0,label:'图书馆'}]);
 */
(function (global) {
  'use strict';

  var VS = [
    'attribute vec2 aPos;',
    'varying vec2 vNdc;',
    'void main(){ vNdc = aPos; gl_Position = vec4(aPos, 0.0, 1.0); }'
  ].join('\n');

  var FS = [
    'precision highp float;',
    'varying vec2 vNdc;',
    'uniform sampler2D uTex;',
    'uniform float uYaw, uPitch, uTanFov, uAspect;',
    'const float PI = 3.141592653589793;',
    'void main(){',
    '  vec2 p = vNdc;',
    '  vec3 d = normalize(vec3(p.x * uTanFov * uAspect, p.y * uTanFov, -1.0));',
    '  float cp = cos(uPitch), sp = sin(uPitch);',
    '  d = vec3(d.x, d.y * cp - d.z * sp, d.y * sp + d.z * cp);',
    '  float cy = cos(uYaw), sy = sin(uYaw);',
    '  d = vec3(d.x * cy + d.z * sy, d.y, -d.x * sy + d.z * cy);',
    '  float u = atan(d.x, -d.z) / (2.0 * PI) + 0.5;',
    '  float v = acos(clamp(d.y, -1.0, 1.0)) / PI;',
    '  gl_FragColor = texture2D(uTex, vec2(u, v));',
    '}'
  ].join('\n');

  var D2R = Math.PI / 180;

  function PanoViewer(container, opts) {
    opts = opts || {};
    this.el = container;
    this.opts = opts;
    this.yaw = 0;           // 弧度，0 = 全景图中心
    this.pitch = 0;
    this.fov = 78;          // 竖直视场角（度）
    this.autoRotate = !!opts.autoRotate;
    this.hotspots = [];
    this._raf = 0;
    this._drag = null;
    this._last = 0;

    var cv = document.createElement('canvas');
    cv.className = 'pv-canvas';
    cv.setAttribute('aria-label', '360 度全景画面');
    container.appendChild(cv);
    this.canvas = cv;

    var st = document.createElement('div');
    st.className = 'pv-status';
    st.textContent = '加载全景…';
    container.appendChild(st);
    this.status = st;

    this.hsLayer = document.createElement('div');
    this.hsLayer.className = 'pv-hotspots';
    container.appendChild(this.hsLayer);

    var cp = document.createElement('div');
    cp.className = 'pv-compass';
    cp.innerHTML = '<span>N</span>';
    container.appendChild(cp);
    this.compass = cp;

    var gl = cv.getContext('webgl2') || cv.getContext('webgl') ||
             cv.getContext('experimental-webgl');
    if (!gl) {
      st.className = 'pv-status pv-error';
      st.textContent = '当前浏览器不支持 WebGL，请使用 Chrome / Edge / Safari 新版本；也可直接打开 01 目录下的全景 JPG 查看。';
      return;
    }
    this.gl = gl;

    var prog = gl.createProgram(), ok = true;
    [['vertex', gl.VERTEX_SHADER, VS], ['fragment', gl.FRAGMENT_SHADER, FS]].forEach(function (s) {
      var sh = gl.createShader(s[1]);
      gl.shaderSource(sh, s[2]); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        ok = false;
        console.error('[PanoViewer] shader', s[0], gl.getShaderInfoLog(sh));
      }
      gl.attachShader(prog, sh);
    });
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      ok = false;
      console.error('[PanoViewer] link', gl.getProgramInfoLog(prog));
    }
    this.prog = prog;
    this.loc = {
      aPos: gl.getAttribLocation(prog, 'aPos'),
      uTex: gl.getUniformLocation(prog, 'uTex'),
      uYaw: gl.getUniformLocation(prog, 'uYaw'),
      uPitch: gl.getUniformLocation(prog, 'uPitch'),
      uTanFov: gl.getUniformLocation(prog, 'uTanFov'),
      uAspect: gl.getUniformLocation(prog, 'uAspect')
    };

    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);

    this.tex = null;
    this.image = null;

    this._bind();
    if (ok) this._resize();
    this._tick = this._tick.bind(this);
    this._raf = requestAnimationFrame(this._tick);
  }

  PanoViewer.prototype._bind = function () {
    var self = this, cv = this.canvas;

    cv.addEventListener('pointerdown', function (e) {
      cv.setPointerCapture(e.pointerId);
      self._drag = { x: e.clientX, y: e.clientY, yaw: self.yaw, pitch: self.pitch };
      self.autoRotatePaused = true;
      cv.classList.add('pv-dragging');
    });
    cv.addEventListener('pointermove', function (e) {
      if (!self._drag) return;
      var k = (self.fov * D2R) / cv.clientHeight;
      self.yaw = self._drag.yaw + (e.clientX - self._drag.x) * k;
      self.pitch = clamp(self._drag.pitch + (e.clientY - self._drag.y) * k, -Math.PI / 2 + 0.05, Math.PI / 2 - 0.05);
    });
    var end = function () { self._drag = null; cv.classList.remove('pv-dragging'); };
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', end);

    cv.addEventListener('wheel', function (e) {
      e.preventDefault();
      self.fov = clamp(self.fov + (e.deltaY > 0 ? 4 : -4), 30, 105);
    }, { passive: false });

    var touches = {};
    cv.addEventListener('touchstart', function (e) {
      if (e.touches.length === 2) {
        touches.d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                               e.touches[0].clientY - e.touches[1].clientY);
        touches.fov = self.fov;
      }
    }, { passive: true });
    cv.addEventListener('touchmove', function (e) {
      if (e.touches.length === 2 && touches.d) {
        var d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                           e.touches[0].clientY - e.touches[1].clientY);
        self.fov = clamp(touches.fov * touches.d / d, 30, 105);
        e.preventDefault();
      }
    }, { passive: false });

    if (global.ResizeObserver) {
      this._ro = new ResizeObserver(function () { self._resize(); });
      this._ro.observe(this.el);
    } else {
      global.addEventListener('resize', function () { self._resize(); });
    }

    this.el.addEventListener('keydown', function (e) {
      var step = 3 * D2R;
      if (e.key === 'ArrowLeft') self.yaw -= step;
      else if (e.key === 'ArrowRight') self.yaw += step;
      else if (e.key === 'ArrowUp') self.pitch = clamp(self.pitch + step, -1.5, 1.5);
      else if (e.key === 'ArrowDown') self.pitch = clamp(self.pitch - step, -1.5, 1.5);
      else if (e.key === '+' || e.key === '=') self.fov = clamp(self.fov - 4, 30, 105);
      else if (e.key === '-') self.fov = clamp(self.fov + 4, 30, 105);
      else return;
      e.preventDefault();
    });
  };

  PanoViewer.prototype._resize = function () {
    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(this.el.clientWidth * dpr));
    var h = Math.max(1, Math.round(this.el.clientHeight * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w; this.canvas.height = h;
    }
  };

  PanoViewer.prototype.load = function (src) {
    var self = this;
    this.status.textContent = '加载全景…';
    this.status.classList.remove('pv-error');
    var img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = function () {
      if (self.image !== img) return;
      var gl = self.gl;
      if (!self.tex) self.tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, self.tex);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      self.status.textContent = '';
      self.status.style.opacity = '0';
      self.ready = true;
      self.resizeToImage();
    };
    img.onerror = function () {
      self.status.classList.add('pv-error');
      self.status.textContent = '全景图加载失败：' + src + '\n（若为本地文件，请用本地服务器打开，见 README）';
    };
    this.image = img;
    img.src = src;
  };

  PanoViewer.prototype.resizeToImage = function () {
    var w = this.image ? this.image.naturalWidth : 2, h = this.image ? this.image.naturalHeight : 1;
    if (!this.tex) return;
    if (this.gl.getParameter(this.gl.MAX_TEXTURE_SIZE) < Math.max(w, h)) {
      console.warn('[PanoViewer] 纹理超出硬件上限', w, h);
    }
  };

  PanoViewer.prototype.setHotspots = function (list) {
    this.hotspots = list || [];
    var self = this;
    this.hsLayer.innerHTML = '';
    this.hotspots.forEach(function (h) {
      var b = document.createElement('button');
      b.className = 'pv-hotspot';
      b.type = 'button';
      b.innerHTML = '<i></i><span>' + (h.label || '') + '</span>';
      if (h.onClick) b.addEventListener('click', h.onClick);
      self.hsLayer.appendChild(b);
      h._el = b;
    });
  };

  PanoViewer.prototype.setView = function (lonDeg, latDeg, fov) {
    this.yaw = -(lonDeg || 0) * D2R;
    this.pitch = (latDeg || 0) * D2R;
    if (fov) this.fov = fov;
  };

  PanoViewer.prototype._project = function (lonDeg, latDeg) {
    var lon = lonDeg * D2R, lat = latDeg * D2R;
    var d = [Math.sin(lon) * Math.cos(lat), Math.sin(lat), -Math.cos(lon) * Math.cos(lat)];
    var cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    var d1 = [d[0], d[1] * cp - d[2] * sp, d[1] * sp + d[2] * cp];
    var cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    var d2 = [d1[0] * cy + d1[2] * sy, d1[1], -d1[0] * sy + d1[2] * cy];
    if (d2[2] > -0.0001) return null;
    var tanF = Math.tan(this.fov * 0.5 * D2R);
    var aspect = this.el.clientWidth / Math.max(1, this.el.clientHeight);
    var x = d2[0] / (-d2[2]) / (tanF * aspect);
    var y = d2[1] / (-d2[2]) / tanF;
    if (Math.abs(x) > 1.6 || Math.abs(y) > 1.6) return null;
    return { x: x, y: y };
  };

  PanoViewer.prototype._tick = function (ts) {
    var dt = this._last ? Math.min(50, ts - this._last) : 16;
    this._last = ts;
    if (this.autoRotate && !this._drag && !this.autoRotatePaused) this.yaw += dt * 0.00035;
    this._resize();
    this._draw();
    this._layoutHotspots();
    this._raf = requestAnimationFrame(this._tick);
  };

  PanoViewer.prototype._draw = function () {
    var gl = this.gl;
    if (!gl) return;
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0.055, 0.06, 0.07, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!this.tex) return;
    gl.useProgram(this.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this._buf || (this._buf = this._makeBuf()));
    gl.enableVertexAttribArray(this.loc.aPos);
    gl.vertexAttribPointer(this.loc.aPos, 2, gl.FLOAT, false, 0, 0);
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.uniform1i(this.loc.uTex, 0);
    gl.uniform1f(this.loc.uYaw, this.yaw);
    gl.uniform1f(this.loc.uPitch, this.pitch);
    gl.uniform1f(this.loc.uTanFov, Math.tan(this.fov * 0.5 * D2R));
    gl.uniform1f(this.loc.uAspect, this.canvas.width / this.canvas.height);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (this.compass) {
      this.compass.style.transform = 'rotate(' + (-this.yaw / D2R) + 'deg)';
    }
  };

  PanoViewer.prototype._makeBuf = function () {
    var gl = this.gl, b = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, b);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    return b;
  };

  PanoViewer.prototype._layoutHotspots = function () {
    if (!this.hotspots.length) return;
    var w = this.el.clientWidth, h = this.el.clientHeight;
    for (var i = 0; i < this.hotspots.length; i++) {
      var hs = this.hotspots[i], el = hs._el;
      if (!el) continue;
      var p = this._project(hs.lon, hs.lat);
      if (!p) { el.style.opacity = '0'; el.style.pointerEvents = 'none'; continue; }
      el.style.opacity = '1';
      el.style.pointerEvents = 'auto';
      el.style.transform = 'translate(' + ((p.x * 0.5 + 0.5) * w) + 'px,' + ((0.5 - p.y * 0.5) * h) + 'px) translate(-50%,-100%)';
    }
  };

  PanoViewer.prototype.setAutoRotate = function (on) {
    this.autoRotate = !!on;
    this.autoRotatePaused = false;
  };

  PanoViewer.prototype.destroy = function () {
    cancelAnimationFrame(this._raf);
    if (this._ro) this._ro.disconnect();
    this.el.innerHTML = '';
  };

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }

  global.PanoViewer = PanoViewer;
})(window);
