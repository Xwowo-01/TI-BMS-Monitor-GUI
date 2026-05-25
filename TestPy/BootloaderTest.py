import os
import sys
import time
import signal
from datetime import datetime

import can

# Vector 配置（应用必须已经存在，无法自动创建）
VECTOR_APP_NAME = "VectorTest"
CHANNEL = 0
BITRATE = 1000000

# 文件（必须在同一目录下）
BIN_FILE = "F29_MCAL_src.bin"
FLASH_ADDR = 0x10100000

# 是否启用 CAN 日志文件
ENABLE_CAN_LOG = True

# CAN ID
TX_ID = 0x4E0
RX_ID = 0x4D0

# TransferData
TRANSFER_SIZE = 0x800

# 全局
running = True

# 日志文件
log_file = None
log_filename = None

if ENABLE_CAN_LOG:
    log_filename = f"can_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_file = open(
        log_filename,
        "w",
        encoding="utf-8"
    )

# 创建 CAN
def create_bus():
    try:
        bus = can.interface.Bus(
            interface='vector',
            channel=CHANNEL,
            bitrate=BITRATE,
            app_name=VECTOR_APP_NAME
        )

        if ENABLE_CAN_LOG:
            print(f"\nCAN 日志文件 : {log_filename}\n")

        print("================================================")
        print("总线初始化成功")
        print(f"Vector App Name : {VECTOR_APP_NAME}")
        print(f"Channel         : CH{CHANNEL + 1}")
        print(f"Bitrate         : {BITRATE}")
        print("Classic CAN 模式")
        print("================================================\n")

        return bus

    except Exception as e:
        print("CAN 初始化失败")
        print(e)
        sys.exit(1)

# 写 CAN 日志
def print_can_msg(msg):
    if not ENABLE_CAN_LOG:
        return
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    data_str = ''.join(f'{x:02x}' for x in msg.data)
    log_file.write(
        f"[{timestamp}] "
        f"ID: {msg.arbitration_id} "
        f"(0x{msg.arbitration_id:x}), "
        f"Length: {msg.dlc}\n"
    )
    log_file.write(f"    Data: {data_str}\n")
    log_file.flush()

# 发 CAN
def send_can(bus, data):

    msg = can.Message(
        arbitration_id=TX_ID,
        data=data,
        is_extended_id=False
    )
    bus.send(msg)
    print_can_msg(msg)

# 收 CAN

def recv_can(bus, timeout=3):
    start = time.time()
    while True:
        msg = bus.recv(timeout=0.1)
        if msg is not None:
            print_can_msg(msg)
            if msg.arbitration_id == RX_ID:
                return msg
        if time.time() - start > timeout:
            raise TimeoutError("ECU response timeout")

# 单帧发送

def send_single_frame(bus, payload):
    length = len(payload)
    frame = [length] + payload
    while len(frame) < 8:
        frame.append(0xAA)
    send_can(bus, frame)

# 多帧发送

def send_multi_frame(bus, payload):
    total_len = len(payload)
    ff = [
        0x10 | ((total_len >> 8) & 0x0F),
        total_len & 0xFF
    ]
    ff += payload[:6]
    while len(ff) < 8:
        ff.append(0xAA)
    send_can(bus, ff)
    fc = recv_can(bus)
    if fc.data[0] != 0x30:
        raise Exception("未收到 FlowControl")
    offset = 6
    sn = 1
    while offset < total_len:
        cf = [
            0x20 | (sn & 0x0F)
        ]
        cf += payload[offset:offset + 7]
        while len(cf) < 8:
            cf.append(0xAA)
        send_can(bus, cf)
        offset += 7
        sn += 1
        if sn > 0x0F:
            sn = 0
        time.sleep(0.001)

# 自动 ISO-TP 发送
def uds_send(bus, payload):
    if len(payload) <= 7:
        send_single_frame(bus, payload)
    else:
        send_multi_frame(bus, payload)

# Security Key

def calc_key(seed):
    return [0x00, 0x02, 0x0B, 0x0A]

# 加载 BIN
def load_bin():
    if not os.path.exists(BIN_FILE):
        raise FileNotFoundError(BIN_FILE)
    with open(BIN_FILE, "rb") as f:
        data = f.read()
    print("\n================================================")
    print("BIN 文件加载成功")
    print(f"文件名 : {BIN_FILE}")
    print(f"大小   : {len(data)} bytes")
    print("================================================\n")
    return data

# Step 打印
def print_step(title):
    print("\n================================================")
    print(title)
    print("================================================")

# 主刷写流程
def flash():
    global running
    bus = create_bus()
    print("================================================")
    if ENABLE_CAN_LOG:
        print("CAN 报文已写入日志文件")
    else:
        print("CAN 日志记录已关闭")
    print("控制台仅显示刷写流程")
    print("================================================\n")
    time.sleep(1)
    # 1. Extended Session
    print_step("1. 进入 Extended Session")
    uds_send(
        bus,
        [0x10, 0x03]
    )
    recv_can(bus)

    # 2. Programming Session
    print_step("2. 进入 Programming Session")
    uds_send(
        bus,
        [0x10, 0x02]
    )
    recv_can(bus)

    # 3. Security Access
    print_step("3. Security Access")
    uds_send(
        bus,
        [0x27, 0x01]
    )
    seed_resp = recv_can(bus)
    seed = seed_resp.data[3:7]
    print(f"Seed : {seed.hex()}")
    key = calc_key(seed)
    print(
        "Key  : " +
        ''.join(f'{x:02x}' for x in key)
    )
    uds_send(
        bus,
        [0x27, 0x02] + key
    )
    recv_can(bus)

    # 4. Erase Routine
    print_step("4. Erase Flash")
    erase_payload = [
        0x31,
        0x01,
        0xFF,
        0x00,

        0x10,
        0x10,
        0x00,
        0x00,

        0x00,
        0x10,
        0x00,
        0x00
    ]
    uds_send(bus, erase_payload)
    recv_can(bus)

    # 5. 加载 BIN
    firmware = load_bin()
    fw_size = len(firmware)

    # 6. RequestDownload
    print_step("5. Request Download")
    request_download = [
        0x34,
        0x00,
        0x44,

        (FLASH_ADDR >> 24) & 0xFF,
        (FLASH_ADDR >> 16) & 0xFF,
        (FLASH_ADDR >> 8) & 0xFF,
        FLASH_ADDR & 0xFF,

        (fw_size >> 24) & 0xFF,
        (fw_size >> 16) & 0xFF,
        (fw_size >> 8) & 0xFF,
        fw_size & 0xFF
    ]
    uds_send(bus, request_download)
    recv_can(bus)

    # 7. TransferData
    print_step("6. Transfer Data")
    offset = 0
    block_counter = 1
    start_time = time.time()
    while offset < fw_size:
        chunk = firmware[offset:offset + TRANSFER_SIZE]
        payload = [
            0x36,
            block_counter
        ] + list(chunk)
        uds_send(bus, payload)
        recv_can(bus)
        offset += len(chunk)
        progress = (offset / fw_size) * 100
        print(
            f"\r下载进度: {progress:.1f}% "
            f"({offset}/{fw_size} bytes)",
            end=""
        )
        block_counter += 1
        if block_counter > 0xFF:
            block_counter = 0
    elapsed = time.time() - start_time
    print("\n\nTransferData 完成")
    print(f"耗时 : {elapsed:.2f} 秒")

    # 8. TransferExit
    print_step("7. Transfer Exit")
    uds_send(
        bus,
        [0x37]
    )
    recv_can(bus)

    # 9. ECU Reset
    print_step("8. ECU Reset")
    uds_send(
        bus,
        [0x11, 0x01]
    )
    recv_can(bus)
    print_step("刷写完成")
    running = False
    time.sleep(1)
    bus.shutdown()
    if ENABLE_CAN_LOG and log_file:
        log_file.close()

# Ctrl+C
def signal_handler(sig, frame):
    global running
    running = False
    print("\n正在退出程序...")
    if ENABLE_CAN_LOG and log_file:
        log_file.close()
    sys.exit(0)

# Main
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        flash()
    except TimeoutError as e:
        print("\n================================================")
        print("UDS Timeout")
        print("================================================")
        print(e)
        if ENABLE_CAN_LOG and log_file:
            log_file.close()
    except Exception as e:
        print("\n================================================")
        print("发生异常:")
        print("================================================")
        print(e)
        if ENABLE_CAN_LOG and log_file:
            log_file.close()