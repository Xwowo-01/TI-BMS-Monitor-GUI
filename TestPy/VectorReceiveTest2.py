"""
CAN 报文接收与实时解析工具 (基于 cantools 库解析 DBC)
=====================================================
依赖:
  pip install python-can cantools

DBC 文件: System2.dbc (或其他 .dbc 文件)
"""

import can
import cantools
import time
import signal
import sys
import os

# ================= 配置区域 =================
VECTOR_APP_NAME = 'VectorTest'
CHANNEL_RX = 0
BITRATE_ARB = 1000000
BITRATE_DATA = 1000000

DBC_FILE = "System2.dbc"               # DBC 文件路径
# ============================================

class DbcDatabase:
    """使用 cantools 加载 DBC，支持热更新"""

    def __init__(self, path):
        self.path = path
        self.db = None
        self.mtime = 0
        self.load()

    def needs_reload(self):
        try:
            return os.path.getmtime(self.path) > self.mtime
        except OSError:
            return False

    def load(self):
        print(f"正在使用 cantools 加载 DBC 数据库: {self.path}")
        try:
            # strict=False 忽略如信号超长等非致命错误
            self.db = cantools.database.load_file(self.path, strict=False)
            self.mtime = os.path.getmtime(self.path)
            print(f"成功加载，共 {len(self.db.messages)} 条报文定义。")
        except Exception as e:
            print(f"DBC 加载失败: {e}")
            sys.exit(1)

    def reload_if_changed(self):
        if self.needs_reload():
            print("检测到 DBC 文件更新，重新加载...")
            self.load()

    def get_message(self, frame_id):
        """根据 CAN ID 获取 Message 对象，不存在返回 None"""
        try:
            return self.db.get_message_by_frame_id(frame_id)
        except KeyError:
            return None


# ---------- 显示格式化 ----------
def format_timestamp(ts):
    return f"{ts:.6f}" if ts is not None else "0.000000"

def format_can_type(msg):
    if msg.is_fd:
        fd_type = "CAN FD"
        if msg.bitrate_switch:
            fd_type += " (BRS)"
        return fd_type
    return "CAN 2.0"

def print_message(msg):
    ts = format_timestamp(msg.timestamp)
    can_type = format_can_type(msg)
    dlc = len(msg.data)
    data_hex = ' '.join(f'{b:02X}' for b in msg.data)
    print(f"[{ts}] ID: 0x{msg.arbitration_id:X} | {can_type} | DLC: {dlc} | {data_hex}")

def decode_and_print(msg, db):
    message = db.get_message(msg.arbitration_id)
    if message is None:
        print("  -> 未知报文，无解析定义")
        return

    try:
        # decode_choices=False 返回物理值，枚举我们手动映射
        decoded = message.decode(msg.data, decode_choices=False)
    except Exception as e:
        print(f"  -> 解码失败: {e}")
        return

    if not decoded:
        print("  -> 空报文")
        return

    # 遍历信号定义，获取物理值并显示
    for signal in message.signals:
        name = signal.name
        phys = decoded.get(name)
        if phys is None:
            continue
        unit = signal.unit or ""

        # 枚举处理
        if signal.choices and phys in signal.choices:
            desc = signal.choices[phys]
            print(f"  {name} = {phys}{unit} ({desc})")
        else:
            # 整数不显示多余小数
            if isinstance(phys, float) and abs(phys - round(phys)) < 1e-9:
                phys = int(phys)
            print(f"  {name} = {phys}{unit}")


# ---------- 主程序 ----------
def main():
    db = DbcDatabase(DBC_FILE)

    print(f"正在连接 Vector 设备 (应用名: {VECTOR_APP_NAME})...")
    bus = None
    try:
        bus = can.interface.Bus(
            interface='vector',
            channel=CHANNEL_RX,
            bitrate=BITRATE_ARB,
            data_bitrate=BITRATE_DATA,
            app_name=VECTOR_APP_NAME,
            fd=True
        )
        print(f"接收通道 (CH{CHANNEL_RX + 1}) 初始化成功。")
        print("开始持续接收报文，按 Ctrl+C 停止...\n")

        while True:
            msg = bus.recv(timeout=1.0)
            if msg is not None:
                db.reload_if_changed()          # 热更新
                print_message(msg)
                decode_and_print(msg, db)

    except KeyboardInterrupt:
        print("\n用户中断，正在关闭总线...")
    except can.CanError as e:
        print(f"CAN 总线错误: {e}")
    finally:
        if bus is not None:
            bus.shutdown()
            print("总线连接已关闭。")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    main()