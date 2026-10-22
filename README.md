# TI BMS Monitor GUI

基于 Python、PySide6 和 python-can 的 BMS 上位机，包含电池监控、单体检测、EIS 控制和 UDS Bootloader 刷写功能。

## 当前 Bootloader 配置

默认勾选“使用 VN1610（26774）”，直接使用该序列号设备的物理 CAN1、1 Mbps、传统 CAN，不依赖 Vector 应用映射。完整 CAN 日志默认开启。

取消该选项后，沿用配置管理中的 Vector 应用、通道和波特率。连接 Vector 硬件仍需在 Windows 安装相应驱动。

## 本地开发

当前已验证的环境为 Windows、Python 3.12.1、PySide6 6.10.1、python-can 4.6.1 和 PyInstaller 6.18.0。程序还使用 cantools 和 pyqtgraph。入口为 `Main.py`。

在已安装项目依赖的环境中运行：

```powershell
python Main.py
```

当前 Bootloader 离线回归测试使用模拟 ECU 和 XL 驱动，不操作实际 BMS：

```powershell
python -B -m unittest discover -s TestPy -p 'test_bootloader*.py'
```

`TestPy` 中其余早期手工测试脚本仅供开发参考，部分使用旧协议假设或直接访问硬件。

打包：

```powershell
python -m PyInstaller --noconfirm BatteryMonitor.spec
```

生成的程序、构建缓存、虚拟环境和运行日志保留在本地，不再纳入新的提交。已有历史中的文件和提交均予以保留。
