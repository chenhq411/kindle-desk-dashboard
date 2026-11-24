# 安装与 USB 接入

## 1. 先准备 Windows

支持目标为 Windows 11 x64，实测 Python 3.14.5。安装 Python，启用系统 OpenSSH 客户端。NVIDIA 监控依赖已安装驱动提供的 `nvidia-smi`；没有 NVIDIA 或接口不可用时 GPU 显示 N/A。

在解压后的项目目录创建 `.venv`，按 README 安装依赖。可以先启动电脑预览；默认 `device_enabled=false`，不会自动连接或改造 Kindle。管理端仅允许本机访问，不需要开放入站防火墙端口。

## 2. 设备前提与范围

当前只实测 PW3（第七代）5.16.2.1.1。先在设备信息页核验，勿公开完整序列号。屏幕应为 1072×1448、8-bit 灰度；显示验证脚本还会实际查询 `eips -i`，不匹配则拒绝发送测试图。

本仓库不实施越狱或刷机，也不附带相关二进制。需要越狱的用户先阅读 [Kindle Modding](https://kindlemodding.org/) 的当前资料，按自己的机型、固件及数据备份需求处理；不要把本项目的实测组合当成其他设备的操作指南。

实测 USBNetwork 为 0.22.N-r19297，传统目录 `/mnt/us/usbnet`，Dropbear SSH、USB 网络启用，Wi-Fi SSH 不启用。原维护者的工具入口见 [NiLuJe 的 MobileRead 工具主题](https://www.mobileread.com/forums/showthread.php?t=225030)。独立核验来源、适用机型和文件完整性；本项目不把可执行包放进 GitHub。

## 3. Windows RNDIS

Kindle 切为 USB 网络模式后，Windows 应识别为 `USB Ethernet/RNDIS Gadget`（可能有 `#2`、`#3` 后缀），硬件标识为 `USB\VID_0525&PID_A4A2`。

如果误识别为 USB 串行设备，不要盲目给其他串口替换驱动。先确认硬件 ID，再通过 Windows Update 或 Microsoft Update Catalog 取得对应 Windows 架构、硬件 ID 且签名有效的 RNDIS 驱动。微软资料：[RNDIS 驱动概览](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/remote-ndis--rndis-)。不要使用随机网盘驱动，不要关闭全局驱动签名保护。

如果出现“设备描述符请求失败”，先查数据线、端口和设备管理器里的真实故障设备；它不等同于 RNDIS 缺驱动。

## 4. 固定 IP 与 SSH

| 端点 | 地址 |
|---|---|
| Windows 的 Kindle USB 网络接口 | 192.168.15.201/24 |
| Kindle USBNetwork | 192.168.15.244 |
| SSH | TCP 22 |

只给 Kindle USB 网卡设置上述地址，不设置默认网关；不要改 Wi-Fi、VPN 或其他网卡。当前传输代码以该固定地址为前提。存在相同子网、特定 VPN 路由或多个活动 Kindle 接口时，检查工具会拒绝继续，需先解决冲突。

可在 Windows 网络设置中为已核实的 Kindle 网卡设定 IPv4；也可从管理员 PowerShell 运行项目的窄范围配置工具：

```powershell
.\.venv\Scripts\python.exe scripts\recover_usb_port.py --configure
```

此命令只处理确认硬件 ID 的 Kindle 网卡。它还尝试项目密钥 SSH 验证：首次安装尚未生成密钥时，IP 设置可能已经完成，但最后 SSH 检查会报错；请保留结果并完成下一步，不能把它误认为整套系统已通过。

普通 PowerShell 运行：

```powershell
.\.venv\Scripts\python.exe scripts\kindle_display_probe.py
```

脚本会确认直连 USB 路由，创建独立 Ed25519 密钥，仅向 USBNetwork 的 `authorized_keys` 追加公钥，并在项目自己的 `known_hosts` 保存首次看到的主机密钥。首次连接属于首次信任，请先确认这确为直连 Kindle；之后主机密钥变化会被 SSH 拒绝。

首次登录可能需要交互式密码。脚本提示按 Enter 的情况对应实测的原装 USBNetwork 空密码配置；若你已设置密码，应输入自己的密码，不能据此清空或重设设备密码。不要把密码、私钥或完整设备标识发到 Issue。

脚本显示成功后，**仍需人工确认 Kindle 图像**：四边完整、中文可读、方向正确、16 阶灰度无异常。可使用 `--stability-minutes 30` 进行至少 30 分钟通信采样，再做物理拔插与重试。自动返回成功不代表目视或断线恢复已通过。

## 5. 部署和停止显示客户端

普通 PowerShell：

```powershell
.\.venv\Scripts\python.exe scripts\run_dashboard.py --setup-kindle
```

该操作上传 `kindle/scripts/KDD_client.sh` 至 `/mnt/us/kdd`，核验哈希及 shell 语法，保留一份已有客户端，再后台启动。它临时停止阅读 GUI 并控制休眠相关状态，正常退出时恢复。它不会安装 Kindle 开机启动项或修改固件。

90 秒没有主机心跳时显示离线时钟，设备需保持供电或有足够电量；设备关机、重启或客户端退出后不能保证继续走时。离线时间取设备系统时钟，设备时钟偏差会影响显示。

停止：

```powershell
.\.venv\Scripts\python.exe scripts\run_dashboard.py --stop-kindle
```

强制断电或杀死进程不等于正常退出。GUI 没有恢复时先检查 `/mnt/us/kdd/client.log`，勿连续重复部署、改固件或反复切换 USB 模式。

## 6. 登录启动、升级与卸载

双击 `Install-Autostart.cmd`，注册当前用户的 HKCU Run 项。它使用项目 `.venv` 的 `pythonw.exe`；需用户登录后才运行。双击 `Start-Dashboard.cmd` 可重新打开当前本地管理地址。

升级前备份 `data/`、`config/`；保留私钥在本机。不要将别人的演示数据库或配置覆盖到自己的安装。原有待办升级会在需要添加字段时自动备份 SQLite 数据库。

卸载先双击 `Uninstall-Dashboard.cmd`，它移除属于当前项目的登录启动项并请求停止后台/客户端；设备不在线时可能无法停止客户端，需连接后单独执行 `--stop-kindle`。它不删除文件、USBNetwork 或 RNDIS 驱动。不要移动仍有登录启动项指向的项目目录。
