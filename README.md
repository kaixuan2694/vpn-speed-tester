# 网络节点测速工具

一个面向 Windows 的轻量网络节点测速软件，可检测当前出口 IP、节点位置、网页延迟、下载速度和上传速度，并给出直观的速度评价。

## 下载与使用

1. 打开仓库右侧的 **Releases** 页面。
2. 下载 `VPN-Speed-Tester-v1.0.0-windows-x64.zip`。
3. 解压后双击 `VPN-Speed-Tester.exe`，无需安装 Python。
4. 选择代理模式，然后点击“开始测速”。

> Windows 首次运行从网络下载的、尚未进行代码签名的软件时，可能显示 SmartScreen 提示。请确认文件来自本仓库的 Release 后再运行。

## 代理模式

- **自动识别**：优先读取 Windows 系统代理，然后检测常见本地代理端口。
- **系统代理**：使用 Windows 当前系统代理。
- **直连/TUN**：不设置 HTTP 代理，适合直连或 TUN 模式。
- **常见端口**：支持 `7890`、`7897`、`10809` 等本地端口。
- **自定义**：输入自定义 HTTP/HTTPS 代理地址。

## 隐私说明

测速时会访问 Cloudflare、Google、CacheFly 及 IP 地理信息服务。软件不会收集、保存或上传用户配置；测速产生的网络流量会计入你的网络用量。

## 从源码运行

需要 Python 3.10 或更高版本：

```powershell
python vpn_speed_tester.py
```

## 构建 Windows 软件

在 PowerShell 中运行：

```powershell
.\build.ps1
```

生成的可执行文件位于 `dist`，发布压缩包位于 `release`。

## 许可证

[MIT License](LICENSE)
