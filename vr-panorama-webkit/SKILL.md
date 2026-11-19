---
name: vr-panorama-webkit
display_name: "全景网页集成包"
description: 把已提取的全景素材库打包成零依赖、可直接起服务打开的网页集成包：WebP 全景、缩略图、点位 JSON、WebGL 查看器（JS/CSS/HTML）、一览拼版与矢量总平面。当需要把全景素材做成可浏览的网页、在 3D 场景里嵌 360 热点、或把素材整理成交付包给老师同学直接查看时使用。输入目录需含 `01_等距柱状全景_*` 结构；抓切片归 vr-panorama-extractor，本技能不负责联网下载。
---

# 全景网页集成包

输入是已经提取好的素材库，输出是**零依赖、可直接起服务打开**的网页包。不联网抓图、不引 three.js、不挂 CDN。

## 产出形式矩阵

全景照片是位图，**不能矢量化**（连续色阶与纹理无法用路径表达）。"各种格式"按用途分工，而不是把同一张图导出成十种扩展名：

| 形式 | 扩展名 | 用途 | 从哪来 |
|---|---|---|---|
| 网页位图 | `.webp` | 网页环视，体积约为 JPG 的 40% | `scripts/make_web_assets.py` |
| 缩略图 / 拼版 | `.jpg` | 索引页、汇报页、快速认点位 | 同上 |
| 矢量 | `.svg` | 只有平面图、线稿、标注、图标该矢量化；照片不行 | 由建模几何数据或官方平面图重绘 |
| 结构化数据 | `.json` / `.js` | 点位清单，给脚本或其他程序读 | 同上 |
| 代码 | `.js` / `.css` / `.html` | 可跑的查看器与索引页 | `assets/web-kit-template/` |
| 说明 | `.md` | 用途对照、朝向约定、版权 | 手写 |

用户说"矢量图"时，先确认他要的是平面图/线稿还是照片——照片那一半走等距柱状 + 透视切图，不是 SVG。

## 工作流

### 1. 生成网页位图与清单

```bash
python3 scripts/make_web_assets.py --lib <素材库A> --lib <素材库B> --out <输出目录> \
  --eq 2560 --thumb 480 --prefixes p1,p2
```

输入约定：每个 `--lib` 目录下需有 `01_等距柱状全景_*/`。产出：

- `img/equirect/*.webp` 网页全景（默认 2560×1280）
- `img/thumb/*.jpg` 缩略图（默认 480×240）
- `img/contact-sheet.jpg` 全部点位拼版
- `data/points.json` 与 `js/pano-data.js`（`window.PANO_POINTS`）

### 2. 复制模板并替换占位符

```bash
cp -r assets/web-kit-template/js assets/web-kit-template/css <输出目录>/
cp assets/web-kit-template/index.html <输出目录>/
```

把 `index.html` 里的 `{{SITE_TITLE}}`、`{{SITE_SUBTITLE}}` 替换成实际站点名。若有几何数据，再补 `vector/campus-plan.svg` 与 `campus-plan-line.svg`。

### 3. 本地起服务验收

```bash
cd <输出目录> && python3 -m http.server 8000
# 浏览器打开 http://127.0.0.1:8000/
```

核对：卡片数量与清单一致；点开能出 360 画面；筛选与搜索可用；WebGL 不可用时给出提示而不是白屏。

## 查看器实现要点（模板已实现，改动时别破坏）

- 全屏三角形 + 片元着色器做等距柱状采样：`u=atan(d.x,-d.z)/2π+0.5`、`v=acos(d.y)/π`；`v` 与图片行方向必须一致，否则整幅上下颠倒。
- `UNPACK_FLIP_Y_WEBGL=false` 时 `v=0` 对应图片首行；不要同时翻转。
- 热点用 JS 投影成 DOM 元素，不写进着色器，方便加文字和点击。
- **必须通过 http(s) 打开**：`file://` 下浏览器禁止把本地图片上传为 WebGL 纹理，表现为"加载失败"，这不是代码 bug。README 里要给 `python3 -m http.server` 命令。

### 查看器 API

| 方法 | 说明 |
|---|---|
| `new PanoViewer(el, {autoRotate})` | 容器需有确定尺寸且 `position:relative` |
| `.load(src)` | 载入 2:1 等距柱状图（jpg/png/webp 均可） |
| `.setView(lon, lat, fov)` | `lon=0` 为图片中心，`lat` 俯仰，`fov` 竖直视场角（30–105） |
| `.setHotspots([{lon,lat,label,onClick}])` | 球面热点，自动随视角移动、转到背后隐藏 |
| `.setAutoRotate(bool)` | 自动环绕 |
| `.destroy()` | 销毁并清空容器 |

## 交付前自检

- 卡片、清单、图片路径三者一致；缩略图与全景一一对应。
- 查看器在软件渲染（SwiftShader）下可出图；无 WebGL 时有明确降级提示。
- 支持 `index.html#p=<点位ID>` 直达某个点位，便于分享与截图。
- README 写明：本地服务命令、体积与压缩档位、版权限制。

## 版权红线

素材影像著作权属原拍摄者与平台。默认定位是个人学习 / 课程作业 / 建模校核，不得公开转载、二次分发或商用；要公开上线请取得授权或改用自摄素材。
