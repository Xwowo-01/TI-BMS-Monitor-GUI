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

**使用 Vector VN1630A 或 Vector VN1610 前，请先在官方 Vector Hardware Manager（VHM）中注册应用并完成通道映射，再在上位机中选择相应型号并填写相同的应用名。监控和 Bootloader 刷写共用配置页中的 CAN 设置。**

1. 安装与设备和 Windows 版本匹配的官方 **Vector Driver Setup**，按安装器提示完成安装及重启。
2. 插入 CAN 卡后，在 Windows 设备管理器中确认设备没有黄色感叹号，并在 **Vector Hardware Manager** 中确认能看到正确的型号、序列号和物理 CAN 通道。较旧的驱动版本可能使用 Vector Hardware Config 工具。
3. 在 VHM 的应用/通道映射配置中**注册（新建）应用**，例如 `VectorTest`。应用名可自定义，后续必须与上位机填写的名称完全一致。
4. 将该应用的 CAN 通道映射到实际连接 BMS 的设备与物理端口。例如，将应用的第一个 CAN 通道映射到所用 CAN 卡的**物理 CAN1**，并应用配置；多张卡同时连接时还需核对设备序列号。
5. 打开上位机“配置管理”，在“CAN 接口”下拉框中选择 `Vector VN1630A` 或 `Vector VN1610`，在“应用名 / App Name”中填写 VHM 中注册的名称（例如 `VectorTest`），将“通道 / Channel”设为 `0`，填写与 BMS 一致的波特率，再点击 CAN 重连按钮。

以上示例的对应关系为：

| VHM 中的设置 | 上位机中的设置 |
| --- | --- |
| 注册应用 `VectorTest` | 应用名填写 `VectorTest` |
| 该应用的第一个 CAN 通道 → 实际设备的物理 CAN1 | 通道填写 `0`（逻辑通道编号从 0 开始） |

程序虽会尝试自动创建缺失的应用，首次使用仍请按上述步骤在 VHM 中手动注册并核对映射；更换 CAN 卡后也要重新检查映射。

上位机会检查 VHM 实际映射的硬件型号是否与下拉框选择一致，型号不符时会停止连接或刷写。开始刷写前退出旧版上位机，并断开其他占用目标通道的客户端。

若 Hardware Manager 提示 `Failed connecting to localhost` 并进入离线模式，可检查 Windows 服务中的 `vHardwareService` 是否正常运行，必要时使用官方安装包修复驱动和管理组件。上位机报 `XL_ERR_HW_NOT_PRESENT` 时，应检查设备识别情况及应用通道映射。

### PCAN 安装与配置

1. 安装与设备及 Windows 版本匹配的 **PEAK-System Device Driver Setup**，保留所用设备的驱动和 PCAN-Basic 组件。
2. 插入 PCAN 设备，用 **PCAN-View** 确认设备可识别；检查完成后断开该工具的通道连接。
3. 在上位机配置管理中选择 `PCAN`，设置相应通道和波特率。本程序通道 `0` 对应 `PCAN_USBBUS1`，通道 `1` 对应 `PCAN_USBBUS2`。

当前 PCAN 监控代码使用 CAN-FD 初始化，需要支持 CAN-FD 的设备；Bootloader 刷写目前使用 Vector，尚未实现 PCAN 刷写。

## CAN 型号选择与 Bootloader 配置

CAN 卡统一在配置管理页选择，刷写页不再提供独立的 VN1610 选项，也不再固定某个设备序列号、端口或波特率。

| CAN 接口选项 | 监控与刷写行为 |
| --- | --- |
| `Vector VN1630A` | 使用 VHM 应用名和逻辑通道；保留原有 CAN-FD 监控与刷写页 CAN-FD 模式选择 |
| `Vector VN1610` | 使用 VHM 应用名和逻辑通道；监控与刷写均使用传统 CAN，数据域波特率和刷写页 CAN-FD 选项禁用 |
| `PCAN` | 保留现有 CAN-FD 监控，尚不支持 Bootloader 刷写 |

先在配置页选择型号、填写参数并点击“重新连接 CAN”，再到 Bootloader 页选择 BIN 开始刷写。完整日志默认开启，刷写期间配置控件暂时禁用，结束后恢复。

旧版本只保存 `Vector` 的配置会兼容显示为 `Vector VN1630A`，原有应用名、通道和波特率保留；实际使用 VN1610 时需重新选择 `Vector VN1610` 并重连。

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
