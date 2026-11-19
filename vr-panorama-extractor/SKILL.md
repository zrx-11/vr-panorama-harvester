---
name: vr-panorama-extractor
display_name: "全景切片提取"
description: 从公开的 VR 全景网页（krpano / 720yun / 一拳全景等）抓取立方体贴片，重投影为等距柱状全景、透视切图与立方体面，整理成位图素材库。当用户给出 360 全景链接并想把其中的图片拆下来、提取实景参考图、为 3D 建模收集立面与环境素材时使用。只做位图提取与简单矢量重绘，不做网页集成包。
---

# 全景切片提取

把网页上的 VR 全景拆成可交付的图片素材。核心结论：**多数平台的 `tour.xml` 加密，但图片切片不加密**，靠浏览器运行时的网络请求就能拿到真实地址——不要因为配置文件加密就判定拿不到。

## 先判断：能不能拿到

| 现象 | 含义 | 处理 |
|---|---|---|
| `tour.xml` / `data_self.xml` 是 `<encrypted>` 密文 | 只是配置加密 | 不影响，走运行时抓取 |
| 直接访问疑似切片路径返回 200 但 `content-type: text/html` | 伪 404 | 路径猜不中，别继续猜 |
| 返回 567 / 520 / 502 | 防盗链或域名错 | 补 `Referer` 与 UA；域名以 netlog 里的真实 host 为准 |
| 页面 HTML 内有 `scenes` / `panoId` 数组 | 配置未加密 | 先解析它拿到点位名称与 ID，可少抓一半 |

## 工作流

### 1. 抓真实切片地址

```bash
python3 scripts/harvest.py discover "<页面URL>" --keep /tmp/net.json
```

底层用 `chromium --log-net-log` 记录网络事件。**必须带软件渲染参数**，否则 krpano 因无 WebGL 直接报错、一张图都不加载：

```
--headless=new --no-sandbox --disable-gpu --enable-unsafe-swiftshader --use-angle=swiftshader
--virtual-time-budget=25000 --net-log-capture-mode=IncludeSensitive
```

输出里认这几类：
- `.../panos/<场景ID>/l1_f_1_1.jpg` —— 立方体面，`l1` 单面、`l2` 2×2、`l3` 4×4 网格
- `.../imgs/mobile_f.jpg` —— 720yun 的六面，`f/b/l/r/u/d`，常达 2500×2500
- 同目录的 `thumb.jpg` / `preview.jpg` —— 先做点位清单和对照表

先用缩略图把点位认全，再决定下载哪些，避免盲下几百 MB。

### 2. 批量下载与校验

```bash
python3 scripts/harvest.py download /tmp/net.json ./out --referer "https://原站/" --par 8
```

- 带 `Referer` 与浏览器 UA，否则被防盗链拦。
- 下载后逐张校验：`Image.open(p).load()`，捕获 `truncated`。**截断文件必须重下**，否则后续拼接报错中断。

### 3. 重投影成可用格式

```bash
python3 scripts/pano_toolkit.py equirect  <六面目录> out_360.jpg --width 4000
python3 scripts/pano_toolkit.py timeslice out_360.jpg ./slices --dirs 0,90,180,270 --w 1440
python3 scripts/pano_toolkit.py cube      out_360.jpg ./cube --size 2048
```

六面目录须含 `f.jpg b.jpg l.jpg r.jpg u.jpg d.jpg`（同尺寸）。脚本按行分块渲染，可处理 4000×2000 以上而不爆内存。

### 4. 归档三档位图

```
素材库/
├── 01_等距柱状全景_<W>x<H>/   2:1，通用：球体内表面、Blender 环境贴图、PTGui/Pano2VR
├── 02_立方体六面_<S>/         cubemap 原生：CubeTextureLoader、UE/Unity skybox
├── 03_透视切图_<W>x<H>/       每点位 4 方向平面照，立面建模参考
└── 04_索引与说明/            索引.csv、点位对照表、使用说明（朝向约定、版权）
```

三者关系：`02` 是原始切片，`01` 由 `02` 拼接重投影，`03` 由 `01` 裁切。只做环视用 `01`，做贴图参考用 `03`，做天空盒才碰 `02`。

### 5. 矢量部分的边界

**照片不做矢量化**：连续色阶与纹理无法用路径表达，硬转要么失真要么文件爆炸。需要矢量时只做这两类，且必须依据官方平面图或已有建模几何数据重绘：

- 总平面 / 楼栋轮廓 / 道路水系 SVG（可缩放、可做底面参考层与热区）
- 线稿版（白底黑线，供描图叠底）

不要把全景照片逐块描成 SVG。

## 拼接口径（踩过的坑）

- 方向向量：`dx=cos(pitch)*sin(yaw)`, `dy=sin(pitch)`, `dz=cos(pitch)*cos(yaw)`；`yaw=0` 对应 `f` 面。
- 面选择：取绝对值最大的分量；`f/b` 用 `z` 主导，`r/l` 用 `x` 主导，`u/d` 用 `y` 主导。
- 像素映射：`px=(u+1)/2*(W-1)`, `py=(v+1)/2*(H-1)`。**`py` 若写成 `1-(v+1)/2`，整幅图会上下颠倒**——这个符号最容易错。
- **扇形接缝的根因不是朝向，而是面 FOV**：若平台切片单面视场不是严格 90°（带广角/畸变），拼出来在水平面交界处出现伞骨状错位、地平线弯曲。症状是换 `l/r` 顺序或翻转 `yaw` 都同样错。
  - 识别：先看单张 `l1_f` 是否是正常直立的照片；再对比不同朝向方案，若所有方案接缝一样，就是 FOV 问题。
  - 处置：这类点位**不要承诺无缝**；改用透视切图（切在各面中心，规避接缝）作交付主力；或标定实际 FOV 后按非 90° 重投影。
  - 判定依据写进交付说明，避免下游把它当自己的 bug。

## 交付前自检

- 每个点位六面齐全、尺寸一致；拼出的全景上下不颠倒、地平线水平。
- 点位有可读名称（能从 `scenes` 数组拿就拿），否则至少给编号 + 对照表。
- 说明文件写清：格式用途对照、命名与朝向约定、拍摄时间、**版权与使用限制**。

## 版权红线

全景影像著作权属原拍摄者与平台。默认按**个人学习、课程作业、建模校核**定位交付，并在说明文件里明确禁止公开转载、二次分发与商用；若下游要上线展示，提示其取得授权或改用自摄素材。不要把抓下来的图直接当作可自由分发的开放素材。
