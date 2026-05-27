import os
import time
from datetime import datetime
import can
from PySide6.QtCore import (
    QObject,
    Signal,
    QSettings
)
class UDSFlasher(QObject):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    stage_signal = Signal(str)
    finished_signal = Signal(bool)
    TX_ID = 0x4E0
    RX_ID = 0x4D0
    TRANSFER_SIZE = 0x800
    FLASH_ADDR = 0x10100000
    # INIT
    def __init__(self, bin_file, save_log=False):
        super().__init__()
        self.bin_file = bin_file
        self.save_log = save_log
        self.log_file = None
        self.bus = None
        # 读取用户保存的 CAN 配置
        settings = QSettings(
            "BatteryMonitor",
            "CANConfig"
        )
        self.vector_app_name = settings.value(
            "app_name",
            "VectorTest"
        )
        self.channel = int(
            settings.value(
                "channel",
                0
            )
        )
        self.bitrate = int(
            settings.value(
                "arb_bitrate",
                1000000
            )
        )
    # LOG
    def log(self, text):
        self.log_signal.emit(text)
        if self.log_file:
            self.log_file.write(text + "\n")
            self.log_file.flush()
    # CAN
    def create_bus(self):
        self.bus = can.interface.Bus(
            interface='vector',
            channel=self.channel,
            bitrate=self.bitrate,
            app_name=self.vector_app_name,
            fd=True
        )
        self.log(
            f"CAN 初始化成功 "
            f"(App={self.vector_app_name}, "
            f"CH={self.channel}, "
            f"Bitrate={self.bitrate})"
        )
    def send_can(self, data):
        msg = can.Message(
            arbitration_id=self.TX_ID,
            data=data,
            is_extended_id=False
        )
        self.bus.send(msg)
        self.log(
            f"TX 0x{self.TX_ID:X} : "
            + ' '.join(f'{x:02X}' for x in data)
        )
    def recv_can(self, timeout=3):
        start = time.time()
        while True:
            msg = self.bus.recv(timeout=0.1)
            if msg is not None:
                self.log(
                    f"RX 0x{msg.arbitration_id:X} : "
                    + ' '.join(f'{x:02X}' for x in msg.data)
                )
                if msg.arbitration_id == self.RX_ID:
                    return msg
            if time.time() - start > timeout:
                raise TimeoutError(
                    "ECU response timeout"
                )
    # ISO TP
    def send_single_frame(self, payload):
        frame = [len(payload)] + payload
        while len(frame) < 8:
            frame.append(0xAA)
        self.send_can(frame)

    def send_multi_frame(self, payload):
        total_len = len(payload)
        ff = [
            0x10 | ((total_len >> 8) & 0x0F),
            total_len & 0xFF
        ]
        ff += payload[:6]
        while len(ff) < 8:
            ff.append(0xAA)
        self.send_can(ff)
        fc = self.recv_can()
        if fc.data[0] != 0x30:
            raise Exception("未收到 FlowControl")
        offset = 6
        sn = 1
        while offset < total_len:
            cf = [0x20 | (sn & 0x0F)]
            cf += payload[offset:offset + 7]
            while len(cf) < 8:
                cf.append(0xAA)
            self.send_can(cf)
            offset += 7
            sn += 1
            if sn > 0x0F:
                sn = 0
            time.sleep(0.001)

    def uds_send(self, payload):
        if len(payload) <= 7:
            self.send_single_frame(payload)
        else:
            self.send_multi_frame(payload)

    # Security
    def calc_key(self, seed):
        return [0x00, 0x02, 0x0B, 0x0A]

    # FLASH
    def flash(self):
        try:
            if self.save_log:
                filename = (
                    "canlog_"
                    + datetime.now().strftime(
                        "%Y%m%d_%H%M%S"
                    )
                    + ".txt"
                )
                self.log_file = open(
                    filename,
                    "w",
                    encoding="utf-8"
                )
            # 创建 CAN
            self.create_bus()
            self.stage_signal.emit(
                "进入 Extended Session"
            )
            self.uds_send([0x10, 0x03])
            self.recv_can()
            self.stage_signal.emit(
                "进入 Programming Session"
            )
            self.uds_send([0x10, 0x02])
            self.recv_can()
            self.stage_signal.emit(
                "Security Access"
            )
            self.uds_send([0x27, 0x01])
            seed_resp = self.recv_can()
            seed = seed_resp.data[3:7]
            key = self.calc_key(seed)
            self.uds_send(
                [0x27, 0x02] + key
            )
            self.recv_can()
            self.stage_signal.emit(
                "擦除 Flash"
            )
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
            self.uds_send(
                erase_payload
            )
            self.recv_can()
            self.stage_signal.emit("加载 BIN")
            with open(self.bin_file, "rb") as f:
                firmware = f.read()
            fw_size = len(firmware)
            self.stage_signal.emit(
                "Request Download"
            )
            request_download = [
                0x34,
                0x00,
                0x44,

                (self.FLASH_ADDR >> 24) & 0xFF,
                (self.FLASH_ADDR >> 16) & 0xFF,
                (self.FLASH_ADDR >> 8) & 0xFF,
                self.FLASH_ADDR & 0xFF,

                (fw_size >> 24) & 0xFF,
                (fw_size >> 16) & 0xFF,
                (fw_size >> 8) & 0xFF,
                fw_size & 0xFF
            ]
            self.uds_send(
                request_download
            )
            self.recv_can()
            self.stage_signal.emit(
                "Transfer Data"
            )
            offset = 0
            block_counter = 1
            while offset < fw_size:
                chunk = firmware[
                    offset:
                    offset + self.TRANSFER_SIZE
                ]
                payload = [
                    0x36,
                    block_counter
                ] + list(chunk)
                self.uds_send(payload)
                self.recv_can()
                offset += len(chunk)
                progress = int(
                    offset / fw_size * 100
                )
                self.progress_signal.emit(
                    progress
                )
                block_counter += 1
                if block_counter > 0xFF:
                    block_counter = 0
            self.stage_signal.emit(
                "Transfer Exit"
            )
            self.uds_send([0x37])
            self.recv_can()
            self.stage_signal.emit(
                "ECU Reset"
            )
            self.uds_send([0x11, 0x01])
            self.recv_can()
            self.progress_signal.emit(100)
            self.stage_signal.emit(
                "刷写完成"
            )
            self.finished_signal.emit(True)
        except Exception as e:
            self.log(str(e))
            self.finished_signal.emit(False)
        finally:
            if self.bus:
                self.bus.shutdown()
                self.bus = None
            if self.log_file:
                self.log_file.close()