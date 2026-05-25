import can
import time
import signal
import sys
from datetime import datetime, timezone, timedelta

# ================= 配置区域 =================
VECTOR_APP_NAME = 'VectorTest'  # Vector Hardware Config 中创建的应用名
CHANNEL = 0                     # 使用的通道（索引0为CH1，索引1为CH2）
BITRATE_ARB = 1000000           # 仲裁段波特率（根据总线实际配置调整）
BITRATE_DATA = 1000000          # 数据段波特率（CAN FD 使用）

# 待发送的报文参数（来自 Wireshark 解析）
SEND_ID = 0x4E0                 # 报文 ID
SEND_DATA = [0x02, 0x10, 0x03, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA]  # 8 字节数据
# ============================================

def create_bus(channel):
    """创建 CAN 总线实例（支持标准 CAN 和 CAN FD 接收）"""
    try:
        bus = can.interface.Bus(
            interface='vector',
            channel=channel,
            bitrate=BITRATE_ARB,
            data_bitrate=BITRATE_DATA,
            app_name=VECTOR_APP_NAME,
            fd=True   # 启用 FD 模式，可兼容接收标准 CAN
        )
        print(f"总线初始化成功 (CH{channel + 1})，CAN FD 模式已启用。")
        return bus
    except can.CanError as e:
        print(f"总线初始化失败 (CH{channel + 1})！错误: {e}")
        sys.exit(1)

def send_specified_message(bus):
    """发送指定的 CAN 报文（标准 CAN，无 FD）"""
    msg = can.Message(
        arbitration_id=SEND_ID,
        data=SEND_DATA,
        is_extended_id=False,   # 标准 ID
        is_fd=False             # 传统 CAN 帧
    )
    print(f"\n发送报文: ID=0x{SEND_ID:X}, Data=" + ' '.join(f'{b:02X}' for b in SEND_DATA))
    try:
        bus.send(msg)
        print("报文发送完成。\n")
    except can.CanError as e:
        print(f"发送失败: {e}")

def signal_handler(sig, frame):
    """处理 Ctrl+C，优雅退出"""
    print("\n正在退出监听...")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)

    print(f"正在连接 Vector 设备 (应用名: {VECTOR_APP_NAME})...")
    bus = create_bus(CHANNEL)

    # ----- 发送指定的报文一次（已注释）-----
    # send_specified_message(bus)

    # ----- 持续监听总线报文，时间戳显示为北京时间 -----
    print(f"开始监听通道 CH{CHANNEL + 1} 上的所有报文... (按 Ctrl+C 停止)\n")
    beijing_tz = timezone(timedelta(hours=8))  # 北京时区 UTC+8

    try:
        while True:
            msg = bus.recv(timeout=0.5)   # 超时较短，便于响应退出信号
            if msg is not None:
                ts = msg.timestamp if msg.timestamp is not None else time.time()
                # 将 UTC 时间戳转换为北京时间
                dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(beijing_tz)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 保留毫秒

                # 报文类型
                if msg.is_fd:
                    msg_type = "CAN FD" + (" (BRS)" if msg.bitrate_switch else " (no BRS)")
                else:
                    msg_type = "Classic CAN"

                data_hex = ' '.join(f'{b:02X}' for b in msg.data)
                print(f"[{time_str}] {msg_type} | ID: 0x{msg.arbitration_id:X} "
                      f"({msg.arbitration_id}) | DLC: {msg.dlc} | Data: {data_hex}")
    except Exception as e:
        print(f"监听过程中发生错误: {e}")
    finally:
        bus.shutdown()
        print("总线连接已关闭。")

if __name__ == "__main__":
    main()