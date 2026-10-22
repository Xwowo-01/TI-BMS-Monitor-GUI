# TI BMS Monitor GUI

基于 Python、PySide6 和 python-can 的 BMS 上位机，包含电池监控、单体检测、EIS 控制和 UDS Bootloader 刷写功能。

## 使用环境与驱动安装

当前发布程序为 **Windows x64（64 位）** 应用，已在 Windows 11 x64 验证。运行已打包的 `BatteryMonitor.exe` 无需另外安装 Python，需保留同目录的 `_internal` 文件夹；源码运行所需的 Python 环境见下文“本地开发”。

使用实物 CAN 卡前，按设备品牌安装对应的 Windows 驱动：

| CAN 接口 | 需要安装的组件 | 官方下载与说明 |
| --- | --- | --- |
| Vector VN1610、VN1630A 等 | **Vector Driver Setup**，包含设备驱动及 Vector Hardware Manager；源码运行或自行打包时还需准备 **XL Driver Library** 的 64 位 API `vxlapi64.dll` | [Vector Hardware Manager / Driver Setup](https://www.vector.com/en/product/vector-hardware-manager/)、[XL Driver Library](https://www.vector.com/en/business-unit/testing-validation-diagnostics/products/network-interfaces/xl-driver-library/) |
| PEAK PCAN | **PEAK-System Device Driver Setup**，包含设备驱动、PCAN-View 和 PCAN-Basic API；本程序使用 64 位 `PCANBasic.dll` | [PEAK 官方驱动下载](https://www.peak-system.com/support/downloads/drivers/) |

当前发布包随带的 `vxlapi64.dll`、`PCANBasic.dll` 是应用调用接口，**不能代替 Windows 设备驱动**。即使 EXE 可以正常启动，也需要安装对应驱动后才能连接 CAN 卡。

### Vector 安装与配置

1. 安装与设备和 Windows 版本匹配的官方 **Vector Driver Setup**，按安装器提示完成安装及重启。
2. 插入 CAN 卡后，在 Windows 设备管理器中确认设备没有黄色感叹号，并在 **Vector Hardware Manager** 中确认能看到正确的型号、序列号和物理 CAN 通道。较旧的驱动版本可能使用 Vector Hardware Config 工具。
3. 使用监控页面或通用 Vector 刷写配置时，确认应用名与逻辑通道映射正确。例如上位机设置为 `VectorTest`、通道 `0` 时，应将该应用的第一个 CAN 通道映射到实际接线的物理 CAN1。程序会尝试创建缺失的应用，已有映射仍需核对。
4. 当前固定 VN1610 刷写模式按序列号直接选择硬件，无需注册 `VectorTest` 应用，但仍需要正确安装设备驱动。开始刷写前退出旧版上位机，并断开其他占用目标通道的客户端。

若 Hardware Manager 提示 `Failed connecting to localhost` 并进入离线模式，可检查 Windows 服务中的 `vHardwareService` 是否正常运行，必要时使用官方安装包修复驱动和管理组件。上位机报 `XL_ERR_HW_NOT_PRESENT` 时，应检查设备识别情况及应用通道映射。

### PCAN 安装与配置

1. 安装与设备及 Windows 版本匹配的 **PEAK-System Device Driver Setup**，保留所用设备的驱动和 PCAN-Basic 组件。
2. 插入 PCAN 设备，用 **PCAN-View** 确认设备可识别；检查完成后断开该工具的通道连接。
3. 在上位机配置管理中选择 `PCAN`，设置相应通道和波特率。本程序通道 `0` 对应 `PCAN_USBBUS1`，通道 `1` 对应 `PCAN_USBBUS2`。

当前 PCAN 监控代码使用 CAN-FD 初始化，需要支持 CAN-FD 的设备；Bootloader 刷写目前使用 Vector，尚未实现 PCAN 刷写。

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
