---
name: vr-panorama-harvester
display_name: "VR全景素材拆解"
description: 从公开的 VR 全景网页（krpano / 720yun / 一拳全景等）抓取全景切片，重投影为等距柱状全景与透视切图，按建模参考素材库的格式分批打包。当用户给出一个 VR 全景或 360 全景页面链接并想要其中的图片、想把全景"拆开当素材"、想给 3D 建模或场景复原项目准备实景参考图、或需要把全景转成 three.js 可用的 equirect / cubemap 时使用。
---

# VR全景素材拆解

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
- 同目录的 `thumb.jpg` / `preview.jpg` —— 用于先做点位清单和对照表

先用缩略图把点位认全，再决定下载哪些，避免盲下几百 MB。

### 2. 批量下载

```bash
python3 scripts/harvest.py download /tmp/net.json ./out --referer "https://原站/" --par 8
```

- 带 `Referer` 与浏览器 UA，否则被防盗链拦。
- 下载后逐张校验：`Image.open(p).load()`，捕获 `truncated`。**截断文件必须重下**，否则后续拼接报错中断。

### 3. 转成可用格式

```bash
python3 scripts/pano_toolkit.py equirect  <六面目录> out_360.jpg --width 4000
python3 scripts/pano_toolkit.py timeslice out_360.jpg ./slices --dirs 0,90,180,270 --w 1440
python3 scripts/pano_toolkit.py cube      out_360.jpg ./cube --size 2048
```

六面目录须含 `f.jpg b.jpg l.jpg r.jpg u.jpg d.jpg`（同尺寸）。脚本按行分块渲染，可处理 4000×2000 以上而不爆内存。

### 4. 打包交付

按下游用途分三档，不要只给一堆散图：

```
素材库/
├── 01_等距柱状全景_<W>x<H>/   2:1，通用：three.js 球体内表面、Blender 环境贴图、PTGui/Pano2VR
├── 02_立方体六面_<S>/         cubemap 原生：three.js CubeTextureLoader、UE/Unity skybox
├── 03_透视切图_<W>x<H>/       每点位 4 方向平面照，建模贴图参考最好用
└── 04_索引与说明/            索引.csv、点位对照表、使用说明（含朝向约定、版权）
```

单包体积控制在 150MB 以内；六面单独成包，因为它通常是可选项。

### 5. 产出形式矩阵（"拆成各种格式"到底拆成什么）

全景照片是位图，**不能矢量化**（连续色阶、纹理细节无法用路径表达，代价是失真或文件爆炸）。所以"各种格式"要按用途分工，而不是把同一张图导出成十种扩展名：

| 形式 | 扩展名 | 用途 | 从哪来 |
|---|---|---|---|
| 原始位图 | `.jpg` | 建模贴图参考、打印 | 平台切片 |
| 网页位图 | `.webp` | 网页环视，体积约为 JPG 的 40% | `scripts/make_web_assets.py` |
| 缩略图 / 拼版 | `.jpg` | 索引页、汇报页、快速认点位 | 同上 |
| 矢量 | `.svg` | **只有平面图、线稿、标注、图标该矢量化**；照片不行 | 由建模几何数据或官方平面图重绘 |
| 结构化数据 | `.json` / `.js` | 点位清单、给脚本或其他程序读 | 同上 |
| 代码 | `.js` / `.css` / `.html` | 直接可跑的查看器与索引页 | `assets/web-kit-template/` |
| 说明 | `.md` | 用途对照、朝向约定、版权 | 手写 |

用户说"矢量图"时，先确认他要的是平面图/线稿还是照片——照片那一半要做的是等距柱状 + 透视切图，不是 SVG。

### 6. 网页集成包（默认顺手产出）

素材库不该只给一堆散图。用模板拼一个零依赖网页包：

```bash
python3 scripts/make_web_assets.py --lib <库A> --lib <库B> --out <输出目录> --eq 2560
cp -r assets/web-kit-template/js assets/web-kit-template/css <输出目录>/
cp assets/web-kit-template/index.html <输出目录>/   # 把 {{SITE_TITLE}} 等占位符替换掉
```

产物结构：`index.html`（筛选/搜索/点开即 360 环视）、`js/pano-viewer.js`（零依赖 WebGL 查看器）、`css/`、`data/points.json`、`img/equirect/*.webp`、`img/thumb/*.jpg`、`img/contact-sheet.jpg`。

查看器要点（模板里已实现，改的时候别破坏）：

- 全屏三角形 + 片元着色器做等距柱状采样：`u=atan(d.x,-d.z)/2π+0.5`、`v=acos(d.y)/π`；`v` 与图片行方向必须一致，否则整幅上下颠倒。
- `UNPACK_FLIP_Y_WEBGL=false` 时 `v=0` 对应图片首行；不要同时翻转。
- 热点用 JS 投影成 DOM 元素，不写进着色器，方便加文字和点击。
- **必须通过 http(s) 打开**：`file://` 下浏览器禁止把本地图片上传为 WebGL 纹理，表现为"加载失败"，这不是代码 bug。README 里要给 `python3 -m http.server` 的命令。

## 拼接口径（踩过的坑）

- 方向向量：`dx=cos(pitch)*sin(yaw)`, `dy=sin(pitch)`, `dz=cos(pitch)*cos(yaw)`；`yaw=0` 对应 `f` 面。
- 面选择：取绝对值最大的分量；`f/b` 用 `z` 主导，`r/l` 用 `x` 主导，`u/d` 用 `y` 主导。
- 像素映射：`px=(u+1)/2*(W-1)`, `py=(v+1)/2*(H-1)`。**`py` 若写成 `1-(v+1)/2`，整幅图会上下颠倒**——这个符号最容易错。
- **扇形接缝的根因不是朝向，而是面 FOV**：若平台切片单面视场不是严格 90°（带广角/畸变），拼出来在水平面交界处出现伞骨状错位、地平线弯曲。症状是换 `l/r` 顺序或翻转 `yaw` 都同样错。
  - 识别办法：先看单张 `l1_f` 是否是一张正常直立的照片；再对比不同朝向方案，若所有方案接缝一样，就是 FOV 问题。
  - 处置：这类点位**不要承诺无缝**；改用透视切图（切在各面中心，规避接缝）作交付主力；或标定实际 FOV 后按非 90° 重投影。
  - 判定依据写进交付说明，避免下游把它当自己的 bug。

## 交付前自检

- 每个点位六面齐全、尺寸一致；拼出的全景上下不颠倒、地平线水平。
- 点位有可读名称（能从 `scenes` 数组拿就拿），否则至少给编号 + 对照表。
- 说明文件写清：格式用途对照、命名与朝向约定、拍摄时间、**版权与使用限制**。

## 版权红线

全景影像著作权属原拍摄者与平台。默认按**个人学习、课程作业、建模校核**定位交付，并在说明文件里明确禁止公开转载、二次分发与商用；若下游要上线展示，提示其取得授权或改用自摄素材。不要把抓下来的图直接当作可自由分发的开放素材。
