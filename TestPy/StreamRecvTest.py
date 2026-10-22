"""流式接收自测：用假总线模拟“对端不等请求、按流程连续发送”的 ECU。

跑法： .venv\\Scripts\\python.exe TestPy\\StreamRecvTest.py

场景 1：对端收到第一条请求后，一次性把整段流程（含重复帧/无关帧）全部发出来，
        之后不再发送 -> 验证“收件箱 + 暂存 + 不丢弃”的接收方式能跑完整流程。
场景 2：常规模式（收到请求才应答，含重复帧与迟到应答）-> 验证没有把正常流程改坏。
"""

import os
import sys
import time
import collections

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import can
from PySide6.QtCore import QCoreApplication, Qt

from uds.uds_flasher import UDSFlasher

PAD = 0xAA


def isotp(payload, pad=PAD):
    """把 UDS 负载编码成 ISO-TP 帧列表。"""
    payload = list(payload)
    if len(payload) <= 7:
        frame = [len(payload)] + payload
        while len(frame) < 8:
            frame.append(pad)
        return [frame]
    total = len(payload)
    frame = [0x10 | ((total >> 8) & 0x0F), total & 0xFF] + payload[:6]
    while len(frame) < 8:
        frame.append(pad)
    frames = [frame]
    offset = 6
    sn = 1
    while offset < total:
        cf = [0x20 | (sn & 0x0F)] + payload[offset:offset + 7]
        while len(cf) < 8:
            cf.append(pad)
        frames.append(cf)
        offset += 7
        sn = (sn + 1) & 0x0F
    return frames


def response_for(req):
    """按请求生成对端的应答负载。"""
    sid = req[0]
    if sid == 0x10:
        return [0x50, req[1], 0x00, 0x32, 0x00, 0xC8]
    if sid == 0x27 and len(req) > 1 and req[1] == 0x01:
        return [0x67, 0x01, 0x11, 0x22, 0x33, 0x44]
    if sid == 0x27:
        return [0x67, 0x02]
    if sid == 0x31:
        return [0x71, 0x01, 0xFF, 0x00, 0x10, 0x10, 0x00, 0x00]
    if sid == 0x34:
        return [0x74, 0x20, 0x08, 0x02]      # 最大块长度 0x0802
    if sid == 0x36:
        return [0x76, req[1]]
    if sid == 0x37:
        return [0x77]
    if sid == 0x11:
        return [0x51, 0x01]
    return [0x7F, sid, 0x11]


class FakeBus:
    """假总线：既能“逐条应答”，也能“一次性把所有应答发完（不等请求）”。"""

    def __init__(
        self,
        stream_ahead=False,
        duplicate=False,
        label="",
        delay=0.0,
        no_fc=False,
        lossy=False,
        drop_data_bsc=(),
        drop_ack_bsc=(),
        echo_tx=False
    ):
        self.stream_ahead = stream_ahead
        self.duplicate = duplicate
        self.label = label
        self.delay = delay          # 对端应答延迟（秒）
        self.no_fc = no_fc          # True = 对端从来不回 FlowControl
        self.lossy = lossy          # True = 按块序号严格计数，可模拟丢块/丢应答
        self.echo_tx = echo_tx      # True = 本机发送帧会原样回显在 TX_ID 上
        self.drop_data_bsc = set(drop_data_bsc)   # 这些块对端完全没收到
        self.drop_ack_bsc = set(drop_ack_bsc)     # 这些块对端收下了但应答丢了
        self.ecu_expected = 1       # 对端期望的下一个块序号
        self.block_data = []        # 对端实际写入的数据
        self.dropped_once = set()   # 已经丢过一次的块（重发就能收到）
        self.queue = collections.deque()
        self.tx = []
        self.started = False
        self.pending_ff = None

    def _push(self, frame):
        self.queue.append((time.time() + self.delay, frame))

    # ---- tester -> ECU ----
    def send(self, msg):
        data = bytes(msg.data)
        self.tx.append(data)
        if self.echo_tx:
            # 模拟“板卡/对端把本机发送帧原样回显在本机 TX_ID 上”
            self.queue.append(
                (time.time() + self.delay,
                 can.Message(arbitration_id=UDSFlasher.TX_ID,
                             data=data, is_extended_id=False))
            )
        if self.stream_ahead:
            if not self.started:
                self.started = True
                # 一次性把整段流程全部发出来（不等任何请求）
                for frame in self._ahead_frames():
                    self._push(frame)
            return
        self._reply(data)

    def _reply(self, data):
        frame_type = data[0] & 0xF0
        if frame_type == 0x00:                       # 单帧请求
            req = list(data[1:1 + (data[0] & 0x0F)])
            self._answer(req)
        elif frame_type == 0x10:                     # 首帧请求 -> 立刻回流控
            total = ((data[0] & 0x0F) << 8) | data[1]
            self.pending_ff = {"total": total, "buf": list(data[2:8]), "sn": 1}
            if not self.no_fc:
                self._push(self._fc_frame())
        elif frame_type == 0x20 and self.pending_ff:  # 连续帧
            ff = self.pending_ff
            if (data[0] & 0x0F) != (ff["sn"] & 0x0F):
                return
            ff["buf"] += list(data[1:8])
            ff["sn"] = (ff["sn"] + 1) & 0x0F
            if len(ff["buf"]) >= ff["total"]:
                req = ff["buf"][:ff["total"]]
                self.pending_ff = None
                self._answer(req)

    def _answer(self, req):
        if req[0] == 0x36 and self.lossy:
            self._answer_transfer(req)
            return
        for frame in isotp(response_for(req)):
            self._push(frame)
        if self.duplicate:
            # 对端重复发一遍（日志里看到过重复的 74 应答）
            for frame in isotp(response_for(req)):
                self._push(frame)

    def _answer_transfer(self, req):
        """严格按块序号计数的对端：可模拟“漏收块”和“应答丢失”。"""
        bsc = req[1]
        if bsc != self.ecu_expected:
            self._push_list([0x7F, 0x36, 0x73])       # 块序号错误
            return
        if bsc in self.drop_data_bsc and bsc not in self.dropped_once:
            self.dropped_once.add(bsc)
            return                                   # 这一块的首次发送丢了：不应答、不推进
        self.block_data.append(bytes(req[2:]))
        self.ecu_expected = (bsc + 1) & 0xFF
        if bsc in self.drop_ack_bsc:
            return                                   # 数据收下了，但应答丢了
        self._push_list([0x76, bsc])

    def _push_list(self, payload):
        for frame in isotp(payload):
            self._push(frame)

    @staticmethod
    def _fc_frame():
        return [0x30, 0x00, 0x00, PAD, PAD, PAD, PAD, PAD]

    def _ahead_frames(self):
        """对端脚本：FC + 全部应答（含重复帧、无关帧），一次发完。"""
        frames = [self._fc_frame()]
        script = [
            [0x50, 0x03, 0x00, 0x32, 0x00, 0xC8],
            [0x50, 0x02, 0x00, 0x32, 0x00, 0xC8],
            [0x67, 0x01, 0x11, 0x22, 0x33, 0x44],
            [0x67, 0x02],
            [0x71, 0x01, 0xFF, 0x00, 0x10, 0x10, 0x00, 0x00],
            [0x74, 0x20, 0x08, 0x02],
        ]
        for payload in script:
            frames += isotp(payload)
        frames += isotp([0x74, 0x20, 0x08, 0x02])      # 重复的下载应答
        frames += isotp([0x7F, 0x31, 0x78])            # 无关的否定响应（别的服务）
        for bsc in range(1, 21):
            frames += isotp([0x76, bsc])
        frames += isotp([0x77])
        frames += isotp([0x51, 0x01])
        return frames

    # ---- ECU -> tester ----
    def _msg(self, data):
        return can.Message(
            arbitration_id=UDSFlasher.RX_ID,
            data=data,
            is_extended_id=False
        )

    def recv(self, timeout=0.1):
        now = time.time()
        if self.queue:
            ready_at, frame = self.queue[0]
            if ready_at <= now:
                self.queue.popleft()
                return self._msg(frame)
        time.sleep(min(timeout, 0.005))
        return None

    def shutdown(self):
        pass


def make_firmware(size):
    """生成指定大小的测试固件（内容按字节递增，便于校验）。"""
    data = bytearray()
    while len(data) < size:
        data.append(len(data) & 0xFF)
    with open(BIN_FILE, "wb") as f:
        f.write(bytes(data))


def run_case(
    name,
    stream_ahead,
    duplicate,
    bin_size=5120,
    delay=0.0,
    no_fc=False,
    lossy=False,
    drop_data_bsc=(),
    drop_ack_bsc=(),
    echo_tx=False
):

    make_firmware(bin_size)
    bus = FakeBus(
        stream_ahead=stream_ahead,
        duplicate=duplicate,
        label=name,
        delay=delay,
        no_fc=no_fc,
        lossy=lossy,
        drop_data_bsc=drop_data_bsc,
        drop_ack_bsc=drop_ack_bsc,
        echo_tx=echo_tx
    )
    original_bus = can.interface.Bus
    can.interface.Bus = lambda **kwargs: bus
    logs = []
    try:
        flasher = UDSFlasher(BIN_FILE, save_log=False, fd=False)
        flasher.log_signal.connect(
            logs.append,
            Qt.ConnectionType.DirectConnection
        )
        results = {}
        flasher.finished_signal.connect(
            lambda ok: results.setdefault("ok", ok),
            Qt.ConnectionType.DirectConnection
        )
        flasher.flash()
    finally:
        can.interface.Bus = original_bus

    ok = results.get("ok") is True
    # 数据完整性：对端实际收下的数据必须和固件完全一致
    if ok and bus.block_data:
        fw = open(BIN_FILE, "rb").read()
        written = b"".join(bus.block_data)
        if written != fw[:len(written)] or len(written) != bin_size:
            ok = False
            logs.append(
                f"数据校验失败：对端收到 {len(written)} 字节，"
                f"固件 {bin_size} 字节"
            )
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        for line in logs[-40:]:
            print("   ", line)
    else:
        key_lines = [
            line for line in logs
            if line.startswith(("ECU 允许", "TransferData 完成"))
            or "重发同一块" in line
            or "跳过继续" in line
        ]
        for line in key_lines:
            print("   ", line)
    print(f"    发送帧数 = {len(bus.tx)}")
    return ok


if __name__ == "__main__":
    QCoreApplication(sys.argv)

    BIN_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "_stream_test_fw.bin"
    )

    ok1 = run_case("对端不等请求、连续发送", stream_ahead=True, duplicate=False)
    ok2 = run_case("常规逐条应答 + 重复帧", stream_ahead=False, duplicate=True)
    ok3 = run_case("常规逐条应答", stream_ahead=False, duplicate=False)
    ok4 = run_case("对端不回 FlowControl + 应答迟到 80ms",
                   stream_ahead=False, duplicate=False, delay=0.08, no_fc=True)
    ok5 = run_case("连续发送 + 应答迟到 80ms",
                   stream_ahead=True, duplicate=False, delay=0.08)
    # 对应现场日志：第 3 块对端漏收（无应答）、第 4 块应答丢失（重发报 0x73）
    ok6 = run_case("对端漏收第 3 块 -> 重发同一块",
                   stream_ahead=False, duplicate=False, lossy=True,
                   bin_size=10240, drop_data_bsc={3})
    ok7 = run_case("第 4 块应答丢失 -> 重发报 0x73 后跳过",
                   stream_ahead=False, duplicate=False, lossy=True,
                   bin_size=10240, drop_ack_bsc={4})
    # 本机发送帧被原样回显在 TX_ID 上（现场日志出现过 400+ 条 02 27 01 回显）
    ok8 = run_case("本机帧回显(0x4E0) -> 忽略，不影响刷写",
                   stream_ahead=False, duplicate=False, echo_tx=True,
                   bin_size=5120)

    os.remove(BIN_FILE)
    all_ok = all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8])
    print("\n结果:", "全部通过" if all_ok else "存在失败")
    sys.exit(0 if all_ok else 1)
