# 故障排除

## 启动失败或管理地址变化

先查看 `logs/startup.log` 和 `logs/launcher.log`。管理端口不可用时会自动选择新的本地端口，双击启动器打开，不要只收藏某个固定端口。程序只监听本机，不需要对局域网开放。

缺少依赖时使用 `.venv\Scripts\python.exe -m pip install -r requirements.txt`，不要混用多个 Python。微软雅黑缺失时指定本机可用中文字体路径；本项目不附带微软字体。不要通过全局关闭安全策略解决启动问题。

## Windows USB 无法识别

区分设备描述符错误、串行设备误绑定与 RNDIS 已正常但缺固定 IP。先拔插数据线、换可靠数据线、确认故障确属 Kindle；其他外设的线缆松动也会触发同一 Windows 弹窗。只在确认硬件 ID 后处理相应驱动。

## 换 USB 插口后离线

Windows 可能生成新的 `USB Ethernet/RNDIS Gadget #N`，此前网卡上的固定 IP 不一定迁移。管理员 PowerShell 中运行：

```powershell
.\.venv\Scripts\python.exe scripts\recover_usb_port.py --configure
```

工具只迁移确认属于同一 Kindle USB 硬件的旧非活动接口地址；遇到自定义地址、其他网卡子网冲突或 VPN 特定路由时拒绝修改。随后回到普通 PowerShell：

```powershell
.\.venv\Scripts\python.exe scripts\run_dashboard.py --restart
```

不要反复重装 USBNetwork，不要盲目给所有网卡设相同 IP，不要关闭驱动签名保护。

## SSH 主机密钥变化

不要关闭主机密钥检查。先确认设备确为自己直连的 Kindle，查明重装 USBNetwork 或恢复系统等原因，再人工核实和维护项目 `data/ssh/known_hosts`。不要在 Issue 发出私钥。

## 电脑关机后仍是旧页面

等候约 90 秒。离线时钟要求 `/mnt/us/kdd/KDD_client.sh` 仍在运行、Kindle 有电且设备没有休眠或重启导致客户端停止。先前仅显示过测试 PNG 不代表已经部署常驻客户端。客户端日志位于 `/mnt/us/kdd/client.log`。

## 开机后没有同步

确认已经登录 Windows、登录启动项存在、项目及 `.venv` 没有移动；再检查 USB 网卡、固定 IP、SSH 和设备客户端状态。Kindle 自己重启后当前需要重新部署/启动客户端。不要把 Windows 登录启动和 Kindle 开机启动混为一谈。

## GPU、CPU 或 Codex 显示 N/A

N/A 表示数据缺失，不是硬件故障结论。GPU 使用 NVIDIA SMI；CPU 温度/功耗当前没有传感器集成。Codex 的登录与网络故障见 [数据源说明](CODEX.md)。不要用固定模拟数字替代真实传感器。

## 残影或电量异常

增加全屏清屏频率，保持至少 60 秒自动屏幕周期，观察具体设备表现。当前没有长期残影及电池寿命结论；不要为了追求秒级监控频繁全屏刷新。日常也应检查老旧设备电池外观与温度。
