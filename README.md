# vr-panorama-harvester

把网页上的 VR 全景（krpano / 720yun / 一拳全景等）拆成可直接使用的建模参考素材与网页素材包。

## 它解决什么问题

VR 全景平台的 `tour.xml` 通常是加密的，所以"能不能拿到图"看起来无解。实际结论是：**加密的只是配置，图片切片本身不加密**——用浏览器运行时记录的网络请求就能拿到真实切片地址，再按立方体六面重投影成等距柱状全景，切成透视参考图，最后按用途打包。

## 能力

| 环节 | 脚本 / 资源 | 说明 |
|---|---|---|
| 抓切片地址 | `scripts/harvest.py discover` | chromium `--log-net-log` 抓运行时请求；带软件渲染参数，否则 krpano 无 WebGL 不加载图 |
| 批量下载 | `scripts/harvest.py download` | 带 Referer/UA 绕防盗链；逐张校验截断 |
| 格式转换 | `scripts/pano_toolkit.py` | 六面→等距柱状、透视切图、等距柱状→立方体 |
| 网页素材 | `scripts/make_web_assets.py` | WebP、缩略图、点位清单、拼版 |
| 可跑网页 | `assets/web-kit-template/` | 零依赖 WebGL 查看器 + JS + CSS + 索引页 |

## 安装

把 `vr-panorama-harvester/` 整个目录放进 Agent 的 `workspace/.user_skills/` 下即可。技能名 `vr-panorama-harvester`，中文显示名「VR全景素材拆解」。

## 关键坑（写进 SKILL.md 了）

- 六面的 `v` 行映射写成 `1-(v+1)/2` 会让整幅全景上下颠倒。
- 拼出来出现伞骨状接缝、地平线弯曲，且换朝向、翻转 yaw 都一样 → 是切片单面 **FOV 不等于 90°**，不是朝向错。这类点位不要承诺无缝，改用透视切图。
- `file://` 打开网页会纹理加载失败，必须起本地 http 服务。

## 版权

抓下来的影像著作权属原拍摄者与平台。默认定位是个人学习 / 课程作业 / 建模校核，不得公开转载、二次分发或商用。要公开上线请取得授权或改用自摄素材。
