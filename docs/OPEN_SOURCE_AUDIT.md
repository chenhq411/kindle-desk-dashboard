# 开源研究与实现边界

研究日期：2026-11-24。来源为各仓库 GitHub 元数据、固定提交源码、许可证文件与 Release 列表。以下为整理后的匿名摘要；不包含工作目录内下载的第三方源码。静态研究不等同于在本机运行过所有候选项目。

| 项目 | 审查时提交数 / Release | 许可 | 实际源码功能与本项目取舍 |
|---|---|---|---|
| [kindle-syswatch](https://github.com/Neons921/kindle-syswatch) | 3 / v0.1.0 | 未发现明确 LICENSE | Python/Windows 硬件与 PNG、官方 Codex App Server；只研究，不复制 |
| [paperwhite-weather](https://github.com/estcarisimo/paperwhite-weather) | 51 / v0.1.0 | MIT | 有相同 PW3 固件设备记录，天气渲染与 eips/GUI 生命周期；参考兼容与显示恢复机制 |
| [kindle-dashboard](https://github.com/alexishida/kindle-dashboard) | 28 / v1.0.6 | 未发现明确 LICENSE | Electron/React/SSH、托盘与登录启动；只研究，不引入 Electron 或复制代码 |
| [pad-dash](https://github.com/AsdreamChan/pad-dash) | 93 / 无 | MIT | Python/FastAPI/Pillow、缓存及日历布局、外部 Todoist；本项目采用独立本地 SQLite 待办实现 |
| [headroom-kindle](https://github.com/hamen/headroom-kindle) | 26 / 无 | MIT（字体另为 OFL） | Rust/SSH/eips；研究 USB 传输，未采用其内部网页 Codex 接口 |
| [trmnl-koreader](https://github.com/usetrmnl/trmnl-koreader) | 43 / 无 | MIT | KOReader Lua 插件、远程图像获取与刷新；本项目采用轻量 shell 客户端，无 TRMNL 云端依赖 |
| [KindleVibe](https://github.com/lexrus/KindleVibe) | 22 / 无 | 未发现明确 LICENSE | Go、Session 额度快照及信息排版；只研究，不复制，不把 Token 数量当订阅额度 |

本项目正式 app 由独立 Python 模块实现，使用成熟的 psutil、Pillow、FastAPI、SQLite、Windows 系统 OpenSSH 以及设备已有 USBNetwork/eips。不直接复制上述候选仓库的程序代码；无明确许可证的项目不纳入发行物。

第三方依赖与外部工具保留各自许可，见根目录 THIRD_PARTY_NOTICES.md。公开仓库不携带越狱包、MRPI、USBNetwork、RNDIS 驱动或微软字体。后续若引入外部代码，必须重新核对当时固定版本、许可证及声明要求。
