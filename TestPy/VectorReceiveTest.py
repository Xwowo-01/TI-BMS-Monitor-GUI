"""
CAN 报文接收与实时解析工具 (基于 CSV 数据库)
==============================================
依赖: python-can
安装: pip install python-can

CSV 文件要求:
  - 文件名: CAN信息.csv
  - 编码: UTF-8 (推荐 UTF-8-BOM)
  - 必须包含前两行标题（中文+英文），数据从第三行开始
  - 列顺序与原 Excel 完全一致 (A:报文名称, B:报文类型, C:报文ID, ... U:信号值描述等)

运行: python VectorReceiveTest.py
"""

import can
import time
import signal
import sys
import os
import csv

# ================= 配置区域 =================
VECTOR_APP_NAME = 'VectorTest'          # Vector Hardware Config 应用名
CHANNEL_RX = 0                         # 接收通道 (对应 Vector 硬件配置)
BITRATE_ARB = 1000000                  # 仲裁段波特率
BITRATE_DATA = 1000000                 # 数据段波特率 (CAN FD)

CAN_DB_CSV = "CAN信息.csv"             # CAN 信号数据库 (CSV 格式)
# ============================================

# ---------------- 数值安全转换工具 ----------------
def safe_int(value_str, default=0):
    """尝试将字符串转为 int，失败时返回默认值"""
    try:
        return int(value_str)
    except (ValueError, TypeError):
        return default

def safe_float(value_str, default=1.0):
    """尝试将字符串转为 float，失败时返回默认值"""
    try:
        return float(value_str)
    except (ValueError, TypeError):
        return default

# ---------------- 位提取工具函数 ----------------
def extract_bits(data_bytes, start_byte, start_bit, bit_length, byte_order='Motorola LSB'):
    """
    从 CAN 报文字节数组中提取指定位置的位段，返回整数值。
    支持 Motorola LSB 布局（忽略 byte_order 参数，统一按 Motorola LSB 处理）。
    """
    num_bytes = len(data_bytes)
    byte_idx = start_byte
    bit_idx = start_bit % 8
    bits_left = bit_length
    result = 0
    shift = 0

    while bits_left > 0:
        if byte_idx >= num_bytes:
            break
        byte_val = data_bytes[byte_idx]
        bits_available = 8 - bit_idx
        bits_to_take = min(bits_left, bits_available)

        # 提取位段
        mask = (1 << bits_to_take) - 1
        extracted = (byte_val >> bit_idx) & mask
        result |= (extracted << shift)

        shift += bits_to_take
        bits_left -= bits_to_take

        # 移动到下一个字节（Motorola LSB：地址递增）
        byte_idx += 1
        bit_idx = 0

    return result


def phys_value(raw, resolution, offset):
    """根据精度和偏移量计算物理值"""
    return raw * resolution + offset


# ---------------- CSV 数据库类 ----------------
class CsvDatabase:
    """从 CSV 文件加载 CAN 信号定义，支持热更新"""

    def __init__(self, path):
        self.path = path
        self.signals_by_id = {}  # {arb_id: [signal_dict, ...]}
        self.mtime = 0
        self.load()

    def needs_reload(self):
        """检查文件是否被修改"""
        try:
            return os.path.getmtime(self.path) > self.mtime
        except OSError:
            return False

    def load(self):
        print(f"正在加载数据库: {self.path}")
        signals_map = {}

        with open(self.path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
            if len(rows) < 3:
                print("CSV 文件至少需要包含两行标题和一行数据。")
                sys.exit(1)
            data_rows = rows[2:]  # 跳过前两行标题

        current_id = None
        for row_idx, row in enumerate(data_rows, start=3):
            # 确保行足够长，避免索引越界
            if len(row) < 6:  # 至少需要到 G 列（索引6）
                continue

            msg_name = row[0].strip()          # A: 报文名称
            if msg_name:
                # 新报文开始
                msg_id_str = row[2].strip()    # C: 报文ID
                try:
                    if msg_id_str.lower().startswith('0x'):
                        current_id = int(msg_id_str, 16)
                    else:
                        current_id = int(msg_id_str)
                except ValueError:
                    print(f"警告: 第 {row_idx} 行报文ID无效: {msg_id_str}")
                    current_id = None
                    continue
                if current_id not in signals_map:
                    signals_map[current_id] = []

            if current_id is None:
                continue

            signal_name = row[6].strip()       # G: 信号名称
            if not signal_name:
                continue

            # ---------- 安全提取各字段 ----------
            sig = {
                'name': signal_name,
                'description': row[7].strip() if len(row) > 7 else '',
                'byte_order': row[8].strip() if len(row) > 8 and row[8].strip() else 'Motorola LSB',
                # 数值字段使用安全转换，默认值为 0/1.0
                'start_byte': safe_int(row[9].strip(), 0) if len(row) > 9 else 0,
                'start_bit': safe_int(row[10].strip(), 0) if len(row) > 10 else 0,
                'bit_length': safe_int(row[12].strip(), 0) if len(row) > 12 else 0,
                'data_type': row[13].strip() if len(row) > 13 else '',
                'resolution': safe_float(row[14].strip(), 1.0) if len(row) > 14 else 1.0,
                'offset': safe_float(row[15].strip(), 0.0) if len(row) > 15 else 0.0,
                'unit': row[19].strip() if len(row) > 19 else '',
                'values': {}
            }

            # 解析值描述（枚举）
            if len(row) > 20:
                desc_str = row[20].strip()
                if desc_str:
                    for part in desc_str.split('<br>'):
                        part = part.strip()
                        if ':' in part:
                            key, desc = part.split(':', 1)
                            key = key.strip()
                            desc = desc.strip()
                            try:
                                raw_val = int(key, 16) if key.lower().startswith('0x') else int(key)
                            except ValueError:
                                continue
                            sig['values'][raw_val] = desc

            signals_map[current_id].append(sig)

        self.signals_by_id = signals_map
        self.mtime = os.path.getmtime(self.path)
        print(f"数据库加载完成，共 {len(signals_map)} 个不同 ID 的报文定义。")

    def reload_if_changed(self):
        """如果文件被修改则重新加载"""
        if self.needs_reload():
            print("检测到 CSV 文件更新，重新加载...")
            self.load()

    def get_signals(self, arb_id):
        """返回指定报文 ID 对应的信号列表"""
        return self.signals_by_id.get(arb_id, [])


# ---------------- 报文显示和解码 ----------------
def format_timestamp(ts):
    """格式化时间戳 (秒.微秒)"""
    return f"{ts:.6f}" if ts is not None else "0.000000"

def format_can_type(msg):
    """返回报文类型描述"""
    if msg.is_fd:
        fd_type = "CAN FD"
        if msg.bitrate_switch:
            fd_type += " (BRS)"
        return fd_type
    return "CAN 2.0"

def print_message(msg):
    """打印原始报文信息"""
    ts = format_timestamp(msg.timestamp)
    can_type = format_can_type(msg)
    dlc = len(msg.data)
    data_hex = ' '.join(f'{b:02X}' for b in msg.data)
    print(f"[{ts}] ID: 0x{msg.arbitration_id:X} | {can_type} | DLC: {dlc} | {data_hex}")

def decode_and_print(msg, db):
    """解析并打印报文中的信号"""
    signals = db.get_signals(msg.arbitration_id)
    if not signals:
        print("  -> 未知报文，无解析定义")
        return

    data = list(msg.data)
    for sig in signals:
        raw = extract_bits(data, sig['start_byte'], sig['start_bit'],
                           sig['bit_length'], sig['byte_order'])
        phys = phys_value(raw, sig['resolution'], sig['offset'])
        unit = sig['unit']
        enum_desc = sig['values'].get(raw) if sig['values'] else None

        name = sig['name']
        if enum_desc:
            print(f"  {name} = {phys}{unit} ({enum_desc})")
        else:
            # 避免小数位过多，整数显示为整数
            if isinstance(phys, float) and phys == int(phys):
                phys_disp = int(phys)
            else:
                phys_disp = phys
            print(f"  {name} = {phys_disp}{unit}")


# ---------------- 主程序 ----------------
def main():
    db = CsvDatabase(CAN_DB_CSV)

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
                db.reload_if_changed()          # ← 热更新检测
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
    # 确保 Ctrl+C 时能优雅退出
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    main()