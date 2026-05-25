import can
import time

# ================= 配置区域 =================
VECTOR_APP_NAME = 'VectorTest'  # Vector Hardware Config 中创建的应用名
CHANNEL_TX = 0  # 发送通道 (CH1)
CHANNEL_RX = 1  # 接收通道 (CH2)
BITRATE_ARB = 1000000  # 仲裁段波特率 500 kbps
BITRATE_DATA = 1000000  # 数据段波特率 2 Mbps (仅 CAN FD 使用)

# 传统 CAN 测试报文
CAN_ID_CLASSIC = 0x123
DATA_CLASSIC = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]

# CAN FD 测试报文 (数据长度 >8 字节，使用 BRS)
CAN_ID_FD = 0x456
DATA_FD = [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11,
           0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99]  # 16 字节


# ============================================

def create_bus(channel, is_rx=False):
    """
    创建 CAN 总线实例。
    显式指定 fd=True 以正确启用 CAN FD 模式（解决 IndexError 的关键）。
    """
    try:
        bus = can.interface.Bus(
            interface='vector',
            channel=channel,
            bitrate=BITRATE_ARB,
            data_bitrate=BITRATE_DATA,  # 设置数据段波特率
            app_name=VECTOR_APP_NAME,
            fd=True  # ← 必须显式启用 CAN FD 支持
        )
        role = "接收" if is_rx else "发送"
        print(f"{role}通道 (CH{channel + 1}) 初始化成功 (CAN FD 模式已启用)。")
        return bus
    except can.CanError as e:
        print(f"总线初始化失败 (CH{channel + 1})！错误: {e}")
        raise


def send_and_receive(bus_tx, bus_rx, msg_to_send, description):
    """发送一条报文并等待接收，打印结果"""
    print(f"\n--- {description} 测试 ---")
    print(f"发送报文: {msg_to_send}")
    try:
        bus_tx.send(msg_to_send)
        print("报文已发送，等待接收...")
        time.sleep(0.01)  # 给硬件一点处理时间

        received = bus_rx.recv(timeout=2.0)
        if received is not None:
            print(f"收到报文: {received}")
            if received.arbitration_id == msg_to_send.arbitration_id and received.data == msg_to_send.data:
                print("✅ 测试通过：报文内容完全一致。")
            else:
                print("⚠️ 收到报文，但内容与发送不符。")
        else:
            print("❌ 接收超时，未收到任何报文。")
            print("请检查外部 CAN 线路连接及终端电阻。")
    except can.CanError as e:
        print(f"CAN 通信错误: {e}")


def main():
    print(f"正在连接 Vector 设备 (应用名: {VECTOR_APP_NAME})...")

    # 初始化两个总线实例（发送和接收通道）
    try:
        bus_tx = create_bus(CHANNEL_TX, is_rx=False)
        bus_rx = create_bus(CHANNEL_RX, is_rx=True)
    except can.CanError:
        return

    # ----- 测试 1: 传统 CAN 帧 -----
    classic_msg = can.Message(
        arbitration_id=CAN_ID_CLASSIC,
        data=DATA_CLASSIC,
        is_extended_id=False,
        is_fd=False  # 显式指定为标准 CAN
    )
    send_and_receive(bus_tx, bus_rx, classic_msg, "传统 CAN (Classic CAN)")

    time.sleep(0.5)

    # ----- 测试 2: CAN FD 帧 (带 BRS) -----
    fd_msg = can.Message(
        arbitration_id=CAN_ID_FD,
        data=DATA_FD,
        is_extended_id=False,
        is_fd=True,           # 启用 CAN FD 格式
        bitrate_switch=True   # 使用数据段波特率 (BRS)
    )
    send_and_receive(bus_tx, bus_rx, fd_msg, "CAN FD (数据长度 {})".format(len(DATA_FD)))

    # 关闭总线
    bus_tx.shutdown()
    bus_rx.shutdown()
    print("\n总线连接已关闭。")


if __name__ == "__main__":
    main()