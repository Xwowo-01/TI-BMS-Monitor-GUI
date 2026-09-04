# can_receiver.py
"""
CAN 报文接收模块，封装成 QObject，使用信号通知 GUI。
依赖：python-can, cantools
"""
import cantools
import can

import vector_utils

from PySide6.QtCore import QObject, Signal

# ================= PCAN CAN-FD 时序参数（脚本开头可微调） =================
# 位时间 = nom_brp * (nom_tseg1 + nom_tseg2 + 1) / f_clock
# 例：80 MHz 时钟，nom_brp=1，tseg1=63，tseg2=16 → 80 个 tq → 1 Mbps
PCAN_FD_CLOCK_MHZ = 80      # PCAN 时钟频率（MHz），常见 80 / 60 / 40 / 30 / 24 / 20
PCAN_NOM_BRP = 1            # 仲裁域预分频
PCAN_NOM_TSEG1 = 63         # 仲裁域时间段 1
PCAN_NOM_TSEG2 = 16         # 仲裁域时间段 2
PCAN_NOM_SJW = 16           # 仲裁域同步跳宽
PCAN_DATA_BRP = 1           # 数据域预分频
PCAN_DATA_TSEG1 = 63        # 数据域时间段 1
PCAN_DATA_TSEG2 = 16        # 数据域时间段 2
PCAN_DATA_SJW = 16          # 数据域同步跳宽


class CANReceiver(QObject):
    """CAN 接收器，通过 Notifier 异步接收报文并发射信号"""
    message_received = Signal()
    error_occurred = Signal(str)
    data_updated = Signal(dict)
    raw_message = Signal(object)   # 原始 can.Message（供报文监听显示）
    def __init__(
            self,
            app_name='VectorTest',
            channel=0,
            arb_bitrate=1_000_000,
            data_bitrate=1_000_000,
            dbc_path='System3.dbc',
            interface='vector',
            parent=None
    ):
        super().__init__(parent)
        self.app_name = app_name
        self.channel = channel
        self.arb_bitrate = arb_bitrate
        self.data_bitrate = data_bitrate
        self.dbc_path = dbc_path
        self.interface = interface   # 'vector' 或 'pcan'
        self.bus = None
        self.notifier = None
        self.db = None
        self._load_dbc()
        self._init_bus()

    # 加载 DBC
    def _load_dbc(self):
        print(f"正在加载 DBC: {self.dbc_path}")
        try:
            self.db = cantools.database.load_file(
                self.dbc_path,
                strict=False
            )
            print(
                f"DBC 加载成功，共 "
                f"{len(self.db.messages)} "
                f"条报文定义。"
            )
        except Exception as e:
            msg = f"DBC 加载失败: {e}"
            print(msg)
            self.error_occurred.emit(msg)

    # 初始化总线
    def _init_bus(self):
        try:
            if self.interface == 'vector':
                # 自动确保 Vector 应用存在（不存在则按检测到的硬件自动创建）；
                # 失败不阻断，仍按原逻辑用 app_name 打开总线。
                try:
                    vector_utils.ensure_vector_application(
                        self.app_name,
                        self.channel
                    )
                except Exception as e:
                    print(f"Vector 应用自动创建跳过: {e}")

                self.bus = can.interface.Bus(
                    interface='vector',
                    channel=self.channel,
                    bitrate=self.arb_bitrate,
                    data_bitrate=self.data_bitrate,
                    app_name=self.app_name,
                    fd=True
                )
                chan_desc = f"CH{self.channel + 1}"
            else:
                # PCAN：通道名 PCAN_USBBUS1 / PCAN_USBBUS2 ...，CAN-FD
                channel_name = f"PCAN_USBBUS{self.channel + 1}"
                self.bus = can.interface.Bus(
                    interface='pcan',
                    channel=channel_name,
                    fd=True,
                    f_clock_mhz=PCAN_FD_CLOCK_MHZ,
                    nom_brp=PCAN_NOM_BRP,
                    nom_tseg1=PCAN_NOM_TSEG1,
                    nom_tseg2=PCAN_NOM_TSEG2,
                    nom_sjw=PCAN_NOM_SJW,
                    data_brp=PCAN_DATA_BRP,
                    data_tseg1=PCAN_DATA_TSEG1,
                    data_tseg2=PCAN_DATA_TSEG2,
                    data_sjw=PCAN_DATA_SJW,
                )
                chan_desc = channel_name

            print(
                f"接收通道 "
                f"({chan_desc}) "
                f"初始化成功。"
            )
            self.notifier = can.Notifier(
                self.bus,
                [self._on_message_received]
            )
        except Exception as e:
            msg = f"CAN 总线错误: {e}"
            print(msg)
            self.error_occurred.emit(msg)
            raise RuntimeError(msg)

    # 收到报文
    def _on_message_received(self, msg):
        self.message_received.emit()
        self.raw_message.emit(msg)
        if self.db is not None:
            try:
                decoded = self.db.decode_message(
                    msg.arbitration_id,
                    msg.data
                )
                self.data_updated.emit(decoded)
            except Exception:
                pass

    # 发送一条 CAN 报文
    def send_message(self, arbitration_id, data, is_extended_id=False):
        """发送一条 CAN 报文（默认标准帧），返回是否成功。"""
        if self.bus is None:
            return False
        try:
            msg = can.Message(
                arbitration_id=arbitration_id,
                data=list(data),
                is_extended_id=is_extended_id
            )
            self.bus.send(msg)
            return True
        except Exception as e:
            print(f"CAN 发送失败: {e}")
            return False

    # 停止
    def stop(self):
        if self.notifier:
            self.notifier.stop()
            print("CAN 接收已停止。")
            self.notifier = None
        if self.bus:
            self.bus.shutdown()
            print("总线连接已关闭。")
            self.bus = None

    # 配置获取（可选）
    def get_config(self):
        return {
            "app_name":
                self.app_name,
            "channel":
                self.channel,
            "arb_bitrate":
                self.arb_bitrate,
            "data_bitrate":
                self.data_bitrate,
            "dbc_path":
                self.dbc_path,
            "interface":
                self.interface
        }