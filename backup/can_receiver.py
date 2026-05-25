# can_receiver.py
"""
CAN 报文接收模块，封装成 QObject，使用信号通知 GUI。
依赖：python-can, cantools
"""

import os
import cantools
import can
from PySide6.QtCore import QObject, Signal

class CANReceiver(QObject):
    """CAN 接收器，通过 Notifier 异步接收报文并发射信号"""

    message_received = Signal()          # 收到报文时触发（仅通知，不传数据）
    error_occurred = Signal(str)         # 错误信息
    data_updated = Signal(dict)          # 新增：解码后的信号字典，key=信号名, value=物理值

    def __init__(self, app_name='VectorTest', channel=0, arb_bitrate=1_000_000,
                 data_bitrate=1_000_000, dbc_path='System2.dbc', parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.channel = channel
        self.arb_bitrate = arb_bitrate
        self.data_bitrate = data_bitrate
        self.dbc_path = dbc_path

        self.bus = None
        self.notifier = None
        self.db = None
        self._load_dbc()
        self._init_bus()

    def _load_dbc(self):
        """加载 DBC 文件"""
        print(f"正在加载 DBC: {self.dbc_path}")
        try:
            self.db = cantools.database.load_file(self.dbc_path, strict=False)
            print(f"DBC 加载成功，共 {len(self.db.messages)} 条报文定义。")
        except Exception as e:
            msg = f"DBC 加载失败: {e}"
            print(msg)
            self.error_occurred.emit(msg)

    def _init_bus(self):
        """初始化 Vector CAN 总线"""
        try:
            self.bus = can.interface.Bus(
                interface='vector',
                channel=self.channel,
                bitrate=self.arb_bitrate,
                data_bitrate=self.data_bitrate,
                app_name=self.app_name,
                fd=True
            )
            print(f"接收通道 (CH{self.channel + 1}) 初始化成功。")
            # 使用 Notifier 异步接收，回调中发射信号
            self.notifier = can.Notifier(self.bus, [self._on_message_received])
        except can.CanError as e:
            msg = f"CAN 总线错误: {e}"
            print(msg)
            self.error_occurred.emit(msg)

    def _on_message_received(self, msg):
        """内部回调，每收到一条报文触发一次"""
        # 通知 UI 收到了报文（用于刷新时间等）
        self.message_received.emit()

        # 尝试用 DBC 解码，解码成功则发射信号字典
        if self.db is not None:
            try:
                decoded = self.db.decode_message(msg.arbitration_id, msg.data)
                self.data_updated.emit(decoded)
            except Exception:
                # 解码失败（未定义报文或格式不符），忽略
                pass

    def stop(self):
        """安全停止接收"""
        if self.notifier:
            self.notifier.stop()
            print("CAN 接收已停止。")
        if self.bus:
            self.bus.shutdown()
            print("总线连接已关闭。")