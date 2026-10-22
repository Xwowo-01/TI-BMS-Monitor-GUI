# vector_utils.py
"""
Vector CAN 辅助工具。

1. prepare_vector_dll()
   把打包进 exe 的 vxlapi64.dll 所在目录加入 PATH，使 python-can 的
   can.interfaces.vector.xldriver 能通过 ctypes.util.find_library 找到它。
   Windows 上的 find_library 只搜索 os.environ["PATH"]，不会自动搜索
   PyInstaller 的 _MEIPASS 目录，因此必须显式处理。

2. ensure_vector_application(app_name, channel)
   若 Vector Hardware Config 中不存在指定应用，则按检测到的硬件自动创建，
   从而免去先用官方 Vector Hardware Config 工具手动建应用的步骤。
"""
import os
import sys

# XL_HardwareType.XL_HWTYPE_VIRTUAL 的数值（虚拟通道，非实体硬件）
_HWTYPE_VIRTUAL = 1


def prepare_vector_dll():
    """把打包进 exe 的 CAN DLL（vxlapi64.dll / PCANBasic.dll）所在目录加入 PATH。

    python-can 的 vector / pcan 接口都通过 ctypes.util.find_library 加载 DLL，
    而 Windows 上的 find_library 只搜索 os.environ["PATH"]，不会自动搜索
    PyInstaller 的 _MEIPASS 目录，因此必须显式处理。

    必须在首次 import can.interfaces.vector / can.interfaces.pcan 之前调用。
    返回加入 PATH 的目录（找不到返回 None）。
    """
    if os.name != "nt":
        return None

    dll_names = ("vxlapi64.dll", "PCANBasic.dll")
    candidates = []
    # PyInstaller 冻结环境：onedir 模式下 DLL 位于 sys._MEIPASS（即 _internal）
    if getattr(sys, "_MEIPASS", None):
        candidates.append(sys._MEIPASS)
    # 源码直接运行：与脚本同目录
    candidates.append(os.path.dirname(os.path.abspath(__file__)))

    for directory in candidates:
        if not any(
            os.path.isfile(os.path.join(directory, name)) for name in dll_names
        ):
            continue
        try:
            os.add_dll_directory(directory)  # Python >= 3.8
        except (AttributeError, OSError):
            pass
        path = os.environ.get("PATH", "")
        parts = path.split(os.pathsep) if path else []
        if directory not in parts:
            os.environ["PATH"] = (
                directory + (os.pathsep + path if path else "")
            )
        return directory
    return None


def ensure_vector_application(app_name, channel=0, hw_type=None):
    """确保 Vector Hardware Config 中存在名为 app_name 的应用。

    - 已存在：直接返回 True。
    - 不存在：按 can.detect_available_configs 检测到的硬件自动创建，
      优先实体硬件（排除虚拟通道），返回 True。
    - 检测不到硬件：抛出 RuntimeError（调用方自行兜底）。

    :param app_name: Vector 应用名（对应 UI 中的“应用名”设置）。
    :param channel: 应用内的通道序号（0 起，对应 UI 中的“通道”设置）。
    :param hw_type: 可选的目标硬件型号，自动创建时只选择该型号。
    """
    import can as _can
    from can.interfaces.vector import VectorBus

    # 先枚举硬件（内部会 open/close 驱动，并确保配置可访问）
    configs = _can.detect_available_configs(interfaces=["vector"])

    # 应用已存在则直接返回
    try:
        VectorBus.get_application_config(app_name, channel)
        return True
    except Exception:
        pass

    # 排除虚拟通道，优先实体硬件
    physical = [c for c in configs if c.get("hw_type") != _HWTYPE_VIRTUAL]
    pool = ([c for c in physical if c.get('hw_type') == hw_type]
            if hw_type is not None else physical or configs)
    if not pool:
        raise RuntimeError(
            f"未检测到所选 Vector CAN 硬件（hw_type={hw_type}），无法自动创建应用 '{app_name}'。"
            "请确认已安装 Vector 驱动且硬件已连接。"
        )

    # 选择与请求通道匹配的硬件通道；匹配不到则取第一个
    cfg = None
    for c in pool:
        if c.get("hw_channel") == channel:
            cfg = c
            break
    if cfg is None:
        cfg = pool[0]

    VectorBus.set_application_config(
        app_name=app_name,
        app_channel=channel,
        hw_type=cfg["hw_type"],
        hw_index=cfg["hw_index"],
        hw_channel=cfg["hw_channel"],
    )
    return True


def check_vector_hardware(bus, expected_hw_type):
    """Reject a stale VHM mapping before monitoring or EIS can send frames."""
    import can
    from can.interfaces.vector.canlib import get_channel_configs

    selected = [cfg for cfg in get_channel_configs() if bus.mask & (1 << cfg.channel_index)]
    if len(selected) != 1 or any(int(cfg.hw_type) != expected_hw_type for cfg in selected):
        actual = [(cfg.name, int(cfg.hw_type), cfg.serial_number) for cfg in selected]
        raise can.CanInitializationError(
            f'配置页选择的 Vector 型号与 VHM 映射设备不符：'
            f'expected_hw_type={expected_hw_type} actual={actual!r}；请核对应用名和通道映射')
