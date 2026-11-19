# vr-panorama 技能集

把网页上的 VR 全景拆成可使用的素材，再打包成可运行的网页。两个技能按数据流前后衔接：

```
原站 360 链接
   └─► vr-panorama-extractor（抓切片、重投影、出位图素材库）
          └─► vr-panorama-webkit（WebP / 清单 / 查看器 / 网页包）
```

## 技能目录

### `vr-panorama-extractor` — 全景切片提取

从公开 VR 全景网页（krpano / 720yun / 一拳全景等）抓取立方体贴片，重投影为三档素材：

- `01_等距柱状全景`（2:1，通用环视与环境贴图）
- `02_立方体六面`（cubemap，skybox / CubeTextureLoader 原生格式）
- `03_透视切图`（每点位 4 方向平面照，立面建模参考）

| 资源 | 作用 |
|---|---|
| `scripts/harvest.py` | chromium netlog 抓运行时真实切片地址；批量下载并校验截断 |
| `scripts/pano_toolkit.py` | 六面→等距柱状、透视裁切、等距柱状→立方体 |

### `vr-panorama-webkit` — 全景网页集成包

输入 extractor 产出的素材库，输出零依赖、可直接起服务打开的网页包：

- `img/equirect/*.webp` 网页全景、`img/thumb/*.jpg` 缩略图、一览拼版
- `data/points.json` + `js/pano-data.js` 点位清单
- `js/pano-viewer.js` 手写 WebGL 查看器（不引 three.js、不挂 CDN）
- `css/` + `index.html` 暗色索引页与样式
- `vector/*.svg` 矢量总平面 / 线稿（由几何数据重绘，不是照片矢量化）

| 资源 | 作用 |
|---|---|
| `scripts/make_web_assets.py` | 一键出 WebP、缩略图、清单、拼版 |
| `assets/web-kit-template/` | 查看器 JS、CSS、索引页模板（含 `{{SITE_TITLE}}` 占位符） |

## 安装

把两个目录复制到 Agent 的 `workspace/.user_skills/` 下即可，目录名与技能 slug 保持一致。

## 关键坑（写在各 SKILL.md 里）

- 平台 `tour.xml` 加密 ≠ 图片加密；切片靠浏览器运行时请求就能拿到。
- 六面拼接时 `py` 映射写成 `1-(v+1)/2` 会整幅上下颠倒。
- 拼出伞骨状接缝、地平线弯曲，且换朝向、翻转 yaw 都一样 → 是切片单面 FOV 不等于 90°，不是朝向错；这类点位不要承诺无缝，改用透视切图。
- `file://` 打开网页包会因浏览器跨域策略加载不了 WebGL 纹理，必须起本地 http 服务。
- 照片不可矢量化；SVG 只用于平面图、线稿、标注、图标。

## 版权

抓下来的影像著作权属原拍摄者与平台。默认定位为个人学习 / 课程作业 / 建模校核，不得公开转载、二次分发或商用；要公开上线请取得授权或改用自摄素材。
