import os
import time
import threading
import queue
import hashlib
import platform
from datetime import datetime

import can
from PySide6.QtCore import (
    QObject,
    Signal,
    QSettings
)

# ================= 可调参数（脚本开头可微调） =================
PAD_BYTE = 0xAA          # ISO-TP 填充字节（部分 ECU 要求 0x00 / 0xCC）
RESP_TIMEOUT = 3.0       # 等待应答的超时（秒）
FC_WAIT_TIMEOUT = 1.0    # 每次等待 FlowControl 的超时，超时必须停止发送
FC_MAX_WAIT_S = 5.0     # WAIT 流控累计最多等待时间
FC_MAX_WAIT_FRAMES = 5  # 最多连续接受的 WAIT 数量
RESPONSE_MAX_WAIT_S = 120.0  # 含 NRC 0x78 的单次请求总等待上限
CF_DELAY_S = 0.001       # 连续帧最小间隔（秒）；对端丢块/跟不上时加大到 0.002~0.005
BLOCK_GAP_S = 0.005      # TransferData 每块之间的间隔（秒）
BLOCK_MAX_RETRY = 3      # 每块未收到应答时的重发次数
BLOCK_RETRY_GAP_S = 0.05 # 重发同一块之前的等待（秒）
ECHO_WINDOW = 0.25       # 判断“本机发送帧回显”的时间窗（秒）
PARKED_MAX_AGE = 10.0    # 提前到达的应答最多暂存多久（秒）
CF_LOG_STEP = 64         # 大数据块连续帧日志抽稀步长（避免刷屏）
CF_LOG_THRESHOLD = 256   # 超过该长度的请求才抽稀连续帧日志
PARKED_LOG_LIMIT = 2     # 每次等待最多打印几条“暂存无关应答”日志，其余汇总

# UDS 否定响应码（NRC）含义，便于定位问题
NRC_TEXT = {
    0x10: "通用拒绝",
    0x11: "服务不支持",
    0x12: "子功能不支持",
    0x13: "报文长度或格式错误",
    0x14: "响应过长",
    0x21: "忙，请稍后重试",
    0x22: "条件不满足",
    0x24: "请求序列错误",
    0x31: "请求超出范围",
    0x33: "安全访问被拒绝",
    0x35: "密钥无效",
    0x36: "超过尝试次数",
    0x37: "要求延时",
    0x70: "上传下载未接受",
    0x71: "传输数据暂停",
    0x72: "擦除或编程失败",
    0x73: "块序号错误",
    0x78: "请求已收到，响应挂起",
}


class ResponsePendingTimeout(TimeoutError):
    """ECU 已接收请求但处理超时，禁止自动重发擦除/编程请求。"""


class UDSNegativeResponse(RuntimeError):
    def __init__(self, payload):
        self.sid = payload[1]
        self.nrc = payload[2]
        super().__init__(f"ECU 否定响应: 服务 0x{self.sid:02X}, "
                         f"NRC 0x{self.nrc:02X} ({NRC_TEXT.get(self.nrc, '未知')})")


class UDSFlasher(QObject):
    """后台持续收帧；严格遵守 ISO-TP 流控，只接受当前请求的应答。"""

    log_signal = Signal(str)
    progress_signal = Signal(int)
    stage_signal = Signal(str)
    finished_signal = Signal(bool)
    TX_ID = 0x4E0
    RX_ID = 0x4D0
    TRANSFER_SIZE = 0x800
    FLASH_ADDR = 0x10100000

    # 应答需要校验“子功能 / 块序号”（应答第 2 字节须与请求一致）的服务
    SUB_MATCH_SIDS = (0x10, 0x11, 0x27, 0x28, 0x31, 0x36, 0x37, 0x3E, 0x85)

    # INIT
    def __init__(self, bin_file, save_log=False, fd=False):
        super().__init__()
        self.bin_file = bin_file
        self.save_log = save_log
        self.fd = fd          # True=CAN-FD 模式，False=普通(经典 CAN)
        self.block_size = self.TRANSFER_SIZE   # TransferData 每块字节数（按 ECU 应答调整）
        self.log_file = None
        self.bus = None
        self._transport = None

        # ---- 流式接收架构：后台线程持续收帧，组包后放进收件箱 ----
        self._lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._msgs = []           # 组包完成的 UDS 消息 [(ts, payload)]
        self._parked = []         # 暂存的应答（提前到达 / 暂时不匹配）
        self._fcs = []            # FlowControl [(ts, status, bs, stmin)]
        self._tx_payloads = []    # 本机发送的 UDS 负载 [(ts, bytes)]
        self._ff = None           # 接收多帧的组包状态
        self._echo_count = 0      # 本机发送帧回显计数（用于抽稀日志）
        self._rx_stop = threading.Event()
        self._rx_thread = None
        self._rx_error = None
        self._request_since = 0.0
        self._request_wall = 0.0
        self._request_no = 0
        self._active_request = []
        self._awaiting_fc = False
        self._fc_since = 0.0
        self.p2_timeout = RESP_TIMEOUT
        self.p2_star_timeout = RESP_TIMEOUT
        self._log_lock = threading.Lock()
        self._log_queue = queue.Queue()
        self._log_thread = None
        self._log_error = None
        self._log_seq = 0
        self._started_at = time.perf_counter()
        self._last_tx_at = None
        self._last_cf_at = None
        self.stats = dict(tx=0, tx_failed=0, tx_completed=0, rx=0, error_frames=0, driver_errors=0,
                          max_rx_lag_ms=0.0, max_cf_gap_ms=0.0)

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
        self.data_bitrate = int(
            settings.value(
                "data_bitrate",
                1000000
            )
        )

    # LOG
    def log(self, text, show=True):
        now = time.perf_counter()
        request = self._active_request
        context = f"req={self._request_no}"
        if request:
            context += f" SID=0x{request[0]:02X}"
            if request[0] == 0x36 and len(request) > 1:
                context += f" BSC=0x{request[1]:02X}"
        with self._log_lock:
            self._log_seq += 1
            line = (
                f"[{datetime.now().isoformat(timespec='milliseconds')}] "
                f"[+{now - self._started_at:.6f}s #{self._log_seq:07d} "
                f"{threading.current_thread().name} {context}] {text}"
            )
            if self.log_file and self._log_error is None:
                self._log_queue.put(line)
        if show:
            self.log_signal.emit(line)

    def _write_logs(self):
        """文件 I/O 不占用 CAN 接收线程；周期刷盘，退出前排空。"""
        last_flush = time.perf_counter()
        try:
            while True:
                try:
                    line = self._log_queue.get(timeout=0.25)
                except queue.Empty:
                    self.log_file.flush()
                    continue
                if line is None:
                    break
                self.log_file.write(line + "\n")
                if time.perf_counter() - last_flush >= 0.25:
                    self.log_file.flush()
                    last_flush = time.perf_counter()
            self.log_file.flush()
        except Exception as exc:
            self._log_error = exc
            self.log_signal.emit(f"日志写入失败: {exc}")

    def _close_log(self):
        if self._log_thread is not None:
            self._log_queue.put(None)
            self._log_thread.join()
            self._log_thread = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def _check_rx(self):
        if self._transport is not None:
            self._transport.check_state()
        if self._rx_error is not None:
            raise RuntimeError(f"CAN 接收已中止: {self._rx_error}")

    def _hex(self, data):
        return ' '.join(f'{x:02X}' for x in data)

    @staticmethod
    def _frame_tag(data):
        """给日志加上 ISO-TP 帧类型标注，便于排查错位问题。"""
        if not data:
            return ""
        b0 = data[0]
        frame_type = b0 & 0xF0
        if frame_type == 0x00:
            sid = data[1] if len(data) > 1 else 0
            return f"  [单帧 len={b0 & 0x0F} SID=0x{sid:02X}]"
        if frame_type == 0x10:
            total = ((b0 & 0x0F) << 8) | (data[1] if len(data) > 1 else 0)
            sid = data[2] if len(data) > 2 else 0
            return f"  [首帧 总长={total} SID=0x{sid:02X}]"
        if frame_type == 0x20:
            return f"  [连续帧 SN={b0 & 0x0F}]"
        if frame_type == 0x30:
            status = b0 & 0x0F
            name = {
                0x0: "CTS 允许发送",
                0x1: "WAIT 等待",
                0x2: "OVFLW 溢出",
            }.get(status, "未知")
            bs = data[1] if len(data) > 1 else 0
            stmin = data[2] if len(data) > 2 else 0
            return f"  [流控 {name} BS={bs} STmin={stmin}]"
        return ""

    # CAN
    def create_bus(self):
        from uds.vector_transport import VectorTransport

        settings = QSettings('BatteryMonitor', 'CANConfig')
        interface = settings.value('can_interface', 'vector')
        if interface != 'vector':
            raise ValueError(f'Bootloader 当前发送实现使用 Vector，但设置选择了 {interface}；'
                             '请先选择并配置 Vector，停止向其他接口误发')
        kwargs = dict(
            interface='vector',
            channel=self.channel,
            bitrate=self.bitrate,
            app_name=self.vector_app_name,
            fd=self.fd,
            listen_only=False,
            receive_own_messages=True,
            ignore_config=True,
            # Vector supports one standard hardware filter. A shared mask keeps
            # RX and TX receipts without accepting all traffic into the queue.
            can_filters=[{'can_id': self.RX_ID & self.TX_ID,
                          'can_mask': 0x7FF ^ (self.RX_ID ^ self.TX_ID),
                          'extended': False}],
        )
        if self.fd:
            kwargs['data_bitrate'] = self.data_bitrate
        self.bus = can.interface.Bus(**kwargs)
        self._transport = VectorTransport(self.bus, self.log)
        self._transport.describe()
        self.log(
            f"CAN 初始化成功 "
            f"(App={self.vector_app_name}, "
            f"CH={self.channel}, "
            f"Bitrate={self.bitrate}, "
            f"FD={self.fd})"
        )
        # 启动后台接收线程：全程持续收帧，不依赖请求节奏
        self._start_rx()
        self._transport.request_state()

    def send_can(self, data, note="", show=True):
        msg = can.Message(
            arbitration_id=self.TX_ID,
            data=data,
            is_extended_id=False,
            is_fd=self.fd,
            check=True,
        )
        with self._send_lock:
            started = time.perf_counter()
            gap_ms = ((started - self._last_tx_at) * 1000
                      if self._last_tx_at is not None else 0.0)
            try:
                if self._transport is not None:
                    self._transport.send(msg)
                else:
                    self.bus.send(msg)
            except Exception as exc:
                self.stats['tx_failed'] += 1
                self.log(f"TX_FAILED 0x{self.TX_ID:X} {self._hex(data)}: {exc}")
                raise
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._last_tx_at = started
            self.stats['tx'] += 1
            if data and data[0] & 0xF0 == 0x20:
                if self._last_cf_at is not None:
                    self.stats['max_cf_gap_ms'] = max(
                        self.stats['max_cf_gap_ms'], (started - self._last_cf_at) * 1000)
                self._last_cf_at = started
        tag = ("  [" + note + "]") if note else ""
        tag += self._frame_tag(data)
        self.log(f"TX_QUEUED 0x{self.TX_ID:X} : " + self._hex(data) + tag
                 + f" [call_gap={gap_ms:.3f}ms send_call={elapsed_ms:.3f}ms]", show=show)

    # ---------- 后台接收线程：持续收帧 -> 组包 -> 收件箱 ----------
    def _start_rx(self):
        if self._rx_thread is not None:
            return
        self._rx_stop.clear()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            name="UDS-RX",
            daemon=True
        )
        self._rx_thread.start()

    def _stop_rx(self):
        self._rx_stop.set()
        thread = self._rx_thread
        self._rx_thread = None
        if thread is not None:
            thread.join(timeout=1.0)

    def _rx_loop(self):
        while not self._rx_stop.is_set():
            try:
                msg = self.bus.recv(timeout=0.05)
            except Exception as e:
                if self._rx_stop.is_set():
                    break
                self.stats['driver_errors'] += 1
                self._rx_error = e
                self.log(f"CAN_DRIVER_ERROR: {e!r}")
                break
            if msg is None:
                self._expire()
                continue
            try:
                self._expire()
                self._handle_frame(msg)
            except Exception as e:
                self._rx_error = e
                self.log(f"收帧处理异常: {e}")
                break

    def _expire(self):
        """清理过期数据：暂存太久的应答、迟迟组不完的多帧。"""
        now = time.perf_counter()
        with self._lock:
            self._msgs = [item for item in self._msgs if now - item[0] <= PARKED_MAX_AGE]
            self._parked = [
                item for item in self._parked
                if now - item[0] <= PARKED_MAX_AGE
            ]
            ff = self._ff
            if ff is not None and now > ff["deadline"]:
                self._ff = None
                self.log(
                    f"  (多帧组包超时，已丢弃：应组 {ff['total']} 字节，"
                    f"实收 {len(ff['buf'])} 字节)"
                )

    def _push_msg(self, payload):
        """把一条组包完成的 UDS 消息放进收件箱（本机请求的回显会被过滤）。"""
        if not payload:
            return
        key = bytes(payload)
        now = time.perf_counter()
        with self._lock:
            for ts, sent in self._tx_payloads:
                if sent == key and (now - ts) <= ECHO_WINDOW:
                    self.log("  (本机请求的回显，忽略)")
                    return
            self._msgs.append((now, list(payload)))
            if len(self._msgs) > 256:
                del self._msgs[0]

    def _handle_frame(self, msg):
        data = list(msg.data)
        now = time.perf_counter()
        self.stats['rx'] += 1
        hardware_ts = getattr(msg, 'timestamp', 0.0)
        lag_ms = max(0.0, (time.time() - hardware_ts) * 1000) if hardware_ts > 1e9 else 0.0
        self.stats['max_rx_lag_ms'] = max(self.stats['max_rx_lag_ms'], lag_ms)
        self.log(
            f"RX_RAW 0x{msg.arbitration_id:X} : {self._hex(data)}"
            f" [hw_ts={hardware_ts:.6f} lag={lag_ms:.3f}ms dlc={msg.dlc}"
            f" rx={msg.is_rx} ext={msg.is_extended_id} fd={msg.is_fd}"
            f" error={msg.is_error_frame} remote={msg.is_remote_frame}]",
            show=False,
        )
        if msg.is_error_frame:
            self.stats['error_frames'] += 1
            self.log("CAN_ERROR_FRAME：检测到总线错误帧，详见 RX_RAW")
            return
        if not msg.is_rx:
            if (msg.arbitration_id == self.TX_ID and not msg.is_extended_id
                    and not msg.is_remote_frame):
                self.stats['tx_completed'] += 1
                self.log(f'TX_COMPLETED 0x{self.TX_ID:X} : {self._hex(data)} '
                         f'[hw_ts={hardware_ts:.6f} channel={msg.channel}]', show=False)
            return
        if msg.is_remote_frame or msg.is_extended_id:
            return
        if hardware_ts > 1e9 and hardware_ts < self._request_wall - 0.001:
            self.log("RX_STALE：硬件时间戳早于本次请求，忽略", show=False)
            return
        if msg.arbitration_id == self.TX_ID:
            # 本机发送帧的回显/回环：真正的对端应答永远在 RX_ID 上，直接忽略。
            # （对端/板卡会把我们发出去的帧原样回传，甚至连发几百遍）
            self._echo_count += 1
            if self._echo_count <= 3 or self._echo_count % 50 == 1:
                self.log(
                    f"RX(本机回显，忽略 #{self._echo_count}) "
                    f"0x{msg.arbitration_id:X} : " + self._hex(data)
                )
            return
        if msg.arbitration_id != self.RX_ID:
            self.log(
                f"RX 0x{msg.arbitration_id:X} : "
                + self._hex(data)
                + self._frame_tag(data)
                + "  [非本次刷写 ID，仅记录]"
            )
            return
        self.log(
            f"RX 0x{msg.arbitration_id:X} : "
            + self._hex(data)
            + self._frame_tag(data)
        )
        if not data:
            return
        b0 = data[0]
        frame_type = b0 & 0xF0

        if frame_type == 0x00:                      # 单帧
            if not 1 <= (b0 & 0x0F) <= 7 or len(data) < 1 + (b0 & 0x0F):
                raise ValueError("ISO-TP 单帧长度错误")
            self._push_msg(list(data[1:1 + (b0 & 0x0F)]))
            return

        if frame_type == 0x10:                      # 首帧 -> 回 FlowControl 并开始组包
            if len(data) != 8:
                raise ValueError("ISO-TP 首帧长度错误")
            total_len = ((b0 & 0x0F) << 8) | (
                data[1] if len(data) > 1 else 0
            )
            buf = list(data[2:8])
            if total_len <= len(buf):
                raise ValueError("ISO-TP 首帧声明长度错误")
            with self._lock:
                self._ff = {
                    "total": total_len,
                    "buf": buf,
                    "sn": 1,
                    "deadline": now + RESP_TIMEOUT,
                }
            # 后台接收线程立即回流控，不等待业务线程取应答。
            self.send_flow_control()
            return

        if frame_type == 0x20:                      # 连续帧
            payload = None
            with self._lock:
                ff = self._ff
                if ff is None:
                    self.log("  (无对应首帧的连续帧，仅记录)")
                    return
                if (b0 & 0x0F) != (ff["sn"] & 0x0F):
                    self._ff = None
                    raise ValueError(f"连续帧序号不符：期望 {ff['sn'] & 0x0F}，"
                                     f"收到 {b0 & 0x0F}，中止组包")
                if len(data) < min(8, ff['total'] - len(ff['buf']) + 1):
                    self._ff = None
                    raise ValueError("ISO-TP 连续帧数据长度不足")
                ff["buf"] += list(data[1:8])
                ff["sn"] = (ff["sn"] + 1) & 0x0F
                ff["deadline"] = now + RESP_TIMEOUT
                if len(ff["buf"]) >= ff["total"]:
                    payload = ff["buf"][:ff["total"]]
                    self._ff = None
            if payload is not None:
                self._push_msg(payload)
            return

        if frame_type == 0x30:                      # FlowControl
            if len(data) < 3 or (b0 & 0x0F) > 2:
                raise ValueError("ISO-TP 流控格式错误")
            status = b0 & 0x0F
            bs = data[1] if len(data) > 1 else 0
            stmin = data[2] if len(data) > 2 else 0
            with self._lock:
                if self._awaiting_fc and now >= self._fc_since:
                    self._fcs.append((now, status, bs, stmin))
                else:
                    self.log("FC_IGNORED：当前未等待流控，忽略重复/迟到流控", show=False)
            return

        self.log(f"  (未知帧类型 0x{b0:02X}，仅记录)")

    def send_flow_control(self, bs=0, stmin=0):
        """回 FlowControl：CTS，BS=0（后续连续帧一次发完），STmin 默认 0。"""
        frame = [0x30, bs, stmin]
        while len(frame) < 8:
            frame.append(PAD_BYTE)
        self.send_can(frame, note="回复流控")

    # ---------- 收件箱取用 ----------
    @classmethod
    def _matches(cls, payload, request):
        """判断 payload 是否是 request 的肯定应答（含子功能 / 块序号校验）。"""
        if not payload or not request:
            return False
        if payload[0] != ((request[0] + 0x40) & 0xFF):
            return False
        if len(request) > 1 and request[0] in cls.SUB_MATCH_SIDS:
            if len(payload) < 2 or payload[1] != request[1]:
                return False
        if request[0] == 0x31:
            if len(request) < 4 or len(payload) < 4 or payload[2:4] != request[2:4]:
                return False
        return True

    @staticmethod
    def _is_nrc_for(payload, request):
        """判断 payload 是否是针对本请求的否定响应。"""
        return (
            bool(payload)
            and bool(request)
            and payload[0] == 0x7F
            and len(payload) >= 3
            and payload[1] == request[0]
        )

    def _take(self, request):
        """只取本次请求开始之后收到的应答，保留原始接收时间。"""
        parked_payload = None
        with self._lock:
            for box in (self._parked, self._msgs):
                now = time.perf_counter()
                box[:] = [item for item in box
                          if item[0] >= self._request_since
                          and now - item[0] <= PARKED_MAX_AGE]
                for index, (_, payload) in enumerate(box):
                    if (
                        self._matches(payload, request)
                        or self._is_nrc_for(payload, request)
                    ):
                        del box[index]
                        return payload, None
            if self._msgs:
                received_at, parked_payload = self._msgs.pop(0)
                # 去重 + 封顶：对端会把同一应答连发几十遍，别让暂存区无限膨胀
                key = bytes(parked_payload)
                if not any(bytes(p[1]) == key for p in self._parked):
                    self._parked.append((received_at, parked_payload))
                    if len(self._parked) > 64:
                        del self._parked[0]
        return None, parked_payload

    @staticmethod
    def _is_stale_dup(payload, request):
        """是不是“已经处理过的块”的重复应答。

        对端会把上一块的 76 应答重复发好几遍（日志里见过 76 08 连发 6 遍），
        这类帧既不是本块的应答，也不该占着暂存区，直接丢掉。
        """
        if len(payload) < 2 or len(request) < 2:
            return False
        if payload[0] != 0x76 or request[0] != 0x36:
            return False
        distance = (request[1] - payload[1]) & 0xFF
        return 1 <= distance <= 0x7F

    def _drop_stale_dups(self, request):
        """清掉已处理块的重复应答，返回清掉的条数。"""
        count = 0
        with self._lock:
            for box in (self._parked, self._msgs):
                keep = []
                for item in box:
                    if self._is_stale_dup(item[1], request):
                        count += 1
                    else:
                        keep.append(item)
                box[:] = keep
        return count

    @staticmethod
    def _nrc_message(payload):
        sid = payload[1] if len(payload) > 1 else 0
        nrc = payload[2] if len(payload) > 2 else 0
        return (
            f"ECU 否定响应: 服务 0x{sid:02X}, "
            f"NRC 0x{nrc:02X} ({NRC_TEXT.get(nrc, '未知')})"
        )

    def recv_response(self, request, timeout=None, required=True):
        """等待当前请求；NRC 0x78 延长到 P2*，始终受总等待上限限制。"""
        if isinstance(request, int):
            request = [request]
        timeout = self.p2_timeout if timeout is None else timeout
        expected = (request[0] + 0x40) & 0xFF
        started = time.perf_counter()
        deadline = started + timeout
        hard_deadline = started + max(timeout, RESPONSE_MAX_WAIT_S)
        pending = False
        parked_logs = 0
        parked_total = 0
        stale_total = 0
        while True:
            self._check_rx()
            if time.perf_counter() >= hard_deadline:
                raise ResponsePendingTimeout("请求总等待时间超限，停止自动重发")
            stale_total += self._drop_stale_dups(request)
            payload, parked = self._take(request)
            if parked is not None:
                parked_total += 1
                if parked_logs < PARKED_LOG_LIMIT:
                    parked_logs += 1
                    self.log(
                        f"  (先收到 SID=0x{parked[0]:02X} 的应答，已暂存备用；"
                        f"继续等待 0x{expected:02X})"
                    )
            if payload is not None:
                self._log_noise(parked_total, parked_logs, stale_total)
                if payload[0] == 0x7F:
                    if payload[2] == 0x78:
                        pending = True
                        deadline = min(time.perf_counter() + self.p2_star_timeout,
                                       hard_deadline)
                        self.log(f"UDS_PENDING：ECU 正在处理，继续等待 P2*="
                                 f"{self.p2_star_timeout:.3f}s，总上限 {RESPONSE_MAX_WAIT_S:.1f}s")
                        continue
                    raise UDSNegativeResponse(payload)
                if request[0] == 0x10 and len(payload) >= 6:
                    p2 = ((payload[2] << 8) | payload[3]) / 1000.0
                    p2_star = ((payload[4] << 8) | payload[5]) / 100.0
                    self.p2_timeout = max(RESP_TIMEOUT, p2 + 0.05)
                    self.p2_star_timeout = max(RESP_TIMEOUT, p2_star + 0.05)
                    self.log(f"UDS_TIMING：ECU P2={p2:.3f}s P2*={p2_star:.3f}s；"
                             f"本机等待={self.p2_timeout:.3f}s/{self.p2_star_timeout:.3f}s")
                self.log(f"UDS_ACK：{self._hex(payload)} wait="
                         f"{time.perf_counter() - started:.6f}s")
                return payload
            if time.perf_counter() >= min(deadline, hard_deadline):
                self._log_noise(parked_total, parked_logs, stale_total)
                text = (
                    f"等待应答超时（请求 0x{request[0]:02X}，"
                    f"期望 0x{expected:02X}，已等待 {time.perf_counter() - started:.3f}s，"
                    f"pending={pending}，RX线程存活="
                    f"{self._rx_thread is not None and self._rx_thread.is_alive()}，"
                    f"msgs={len(self._msgs)} FC={len(self._fcs)}）"
                )
                if pending:
                    raise ResponsePendingTimeout(text + "；ECU 尚未确认完成，停止自动重发")
                if required:
                    raise TimeoutError(text)
                self.log(text)
                return None
            time.sleep(0.005)

    def _log_noise(self, parked_total, parked_logs, stale_total):
        """把“暂存/丢弃”的噪声汇总成一行，避免刷屏。"""
        if parked_total > parked_logs:
            self.log(
                f"  (另有 {parked_total - parked_logs} 条无关应答已暂存备用)"
            )
        if stale_total:
            self.log(f"  (丢弃 {stale_total} 条已处理块的重复应答)")

    def pop_flow_control(self, timeout=None):
        """必须收到 CTS 才能发送；WAIT 有数量及累计时间限制。"""
        timeout = FC_WAIT_TIMEOUT if timeout is None else timeout
        started = time.perf_counter()
        deadline = started + timeout
        hard_deadline = started + FC_MAX_WAIT_S
        waits = 0
        while True:
            self._check_rx()
            item = None
            with self._lock:
                if self._fcs:
                    item = self._fcs.pop(0)
            if item is not None:
                _, status, bs, stmin = item
                if status == 0x00:
                    with self._lock:
                        self._awaiting_fc = False
                        self._fcs.clear()
                    self._stmin_seconds(stmin)  # 校验保留值
                    self.log(f"FC_CTS：BS={bs} STmin=0x{stmin:02X} "
                             f"wait={time.perf_counter() - started:.6f}s")
                    return bs, stmin
                if status == 0x01:
                    waits += 1
                    if waits > FC_MAX_WAIT_FRAMES:
                        raise RuntimeError("FlowControl WAIT 次数超限")
                    deadline = min(time.perf_counter() + timeout, hard_deadline)
                    self.log(f"FC_WAIT：第 {waits} 次，继续等待 CTS")
                else:
                    raise RuntimeError("对端 FlowControl=OVFLW（溢出），请求数据过长")
            if time.perf_counter() >= min(deadline, hard_deadline):
                raise TimeoutError(f"FlowControl 超时：{time.perf_counter() - started:.3f}s "
                                   f"未收到 CTS（WAIT={waits}），停止发送连续帧")
            time.sleep(0.005)

    @staticmethod
    def _stmin_seconds(stmin):
        """把 ISO-TP FlowControl 的 STmin 转成秒。"""
        if stmin <= 0x7F:
            return stmin / 1000.0            # 0..127 ms
        if 0xF1 <= stmin <= 0xF9:
            return (stmin - 0xF0) / 10000.0  # 100..900 us
        raise ValueError(f"FlowControl STmin 保留值 0x{stmin:02X}")

    @staticmethod
    def _parse_download_response(payload):
        """解析 RequestDownload 应答(0x74)，返回 ECU 允许的最大块长度。

        应答格式: 74 <lengthFormatIdentifier> <maxNumberOfBlockLength...>
        lengthFormatIdentifier 的高 4 位 = maxNumberOfBlockLength 占几个字节。
        """
        if not payload or payload[0] != 0x74 or len(payload) < 3:
            return None
        lfi = payload[1]
        n = (lfi >> 4) & 0x0F
        if n <= 0 or n > 4 or len(payload) < 2 + n:
            return None
        if n <= 0:
            return None
        value = 0
        for b in payload[2:2 + n]:
            value = (value << 8) | b
        return value

    # ISO TP
    def send_single_frame(self, payload):
        if not 1 <= len(payload) <= 7:
            raise ValueError(f'ISO-TP 单帧长度超出范围: {len(payload)}')
        frame = [len(payload)] + list(payload)
        while len(frame) < 8:
            frame.append(PAD_BYTE)
        self.send_can(frame)

    def send_multi_frame(self, payload):
        payload = list(payload)
        total_len = len(payload)
        if not 8 <= total_len <= 0xFFF:
            raise ValueError(f"ISO-TP 多帧长度超出范围: {total_len}")
        ff = [
            0x10 | ((total_len >> 8) & 0x0F),
            total_len & 0xFF
        ]
        ff += payload[:6]
        while len(ff) < 8:
            ff.append(PAD_BYTE)
        quiet = total_len > CF_LOG_THRESHOLD
        total_cf = (total_len - 6 + 6) // 7
        self._last_cf_at = None
        try:
            self._arm_flow_control()
            self.send_can(ff, note=f"首帧 总长={total_len}")
            bs, stmin = self.pop_flow_control()
            delay = max(self._stmin_seconds(stmin), CF_DELAY_S)
            offset, sn, sent_in_block, cf_index = 6, 1, 0, 0
            while offset < total_len:
                self._check_rx()
                cf = [0x20 | sn] + payload[offset:offset + 7]
                cf += [PAD_BYTE] * (8 - len(cf))
                last = (offset + 7) >= total_len
                boundary = bs > 0 and sent_in_block + 1 >= bs and not last
                # 在触发 ECU 回复 FC 的最后一帧之前开窗，保留即时回复。
                if boundary:
                    self._arm_flow_control()
                show = (not quiet) or last or (cf_index % CF_LOG_STEP == 0)
                self.send_can(cf, note=f"CF={cf_index + 1}/{total_cf} SN={sn} "
                              f"offset={offset} BS={bs} target_gap={delay * 1000:.3f}ms",
                              show=show)
                offset += 7
                sn = (sn + 1) & 0x0F
                sent_in_block += 1
                cf_index += 1
                if not last:
                    time.sleep(delay)
                if boundary:
                    bs, stmin = self.pop_flow_control()
                    delay = max(self._stmin_seconds(stmin), CF_DELAY_S)
                    sent_in_block = 0
            if quiet:
                self.log(f"多帧发送完成：{total_len} 字节，{total_cf} 个 CF；"
                         f"界面每 {CF_LOG_STEP} 帧显示一次，文件保存全部帧")
        finally:
            with self._lock:
                self._awaiting_fc = False
                self._fcs.clear()

    def _arm_flow_control(self):
        with self._lock:
            self._fcs.clear()
            self._fc_since = time.perf_counter()
            self._awaiting_fc = True

    def _drop_flow_controls(self):
        """清空流控队列，返回清掉的条数。"""
        with self._lock:
            count = len(self._fcs)
            self._fcs.clear()
        return count

    def uds_send(self, payload):
        payload = list(payload)
        with self._lock:
            self._tx_payloads.append((time.perf_counter(), bytes(payload)))
            if len(self._tx_payloads) > 64:
                del self._tx_payloads[0]
        if len(payload) <= 7:
            self.send_single_frame(payload)
        else:
            self.send_multi_frame(payload)

    def send_request(self, payload, timeout=None, required=True, retries=1):
        """发起新的事务；本次请求开始前的缓存不能确认本次请求。"""
        payload = list(payload)
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                self._check_rx()
                with self._lock:
                    discarded = len(self._msgs) + len(self._parked) + len(self._fcs)
                    self._msgs.clear()
                    self._parked.clear()
                    self._fcs.clear()
                    self._ff = None
                    self._request_no += 1
                    self._request_since = time.perf_counter()
                    self._request_wall = time.time()
                    self._active_request = payload[:4]
                self.log(f"UDS_REQUEST：attempt={attempt}/{retries} len={len(payload)} "
                         f"discarded_old={discarded} head={self._hex(payload[:16])}")
                self.uds_send(payload)
                return self.recv_response(payload, timeout, required)
            except ResponsePendingTimeout:
                raise
            except TimeoutError as e:
                last_exc = e
                if attempt < retries:
                    self.log(
                        f"  (请求 0x{payload[0]:02X} 第 {attempt} 次无应答，"
                        f"50ms 后重发)"
                    )
                    time.sleep(0.05)
                else:
                    raise
        if last_exc:
            raise last_exc
        return None

    # Security
    def calc_key(self, seed):
        return [0x00, 0x02, 0x0B, 0x0A]

    # FLASH
    def flash(self):
        success = False
        try:
            if self.save_log:
                filename = (
                    "canlog_"
                    + datetime.now().strftime(
                        "%Y%m%d_%H%M%S_%f"
                    )
                    + ".txt"
                )
                self.log_file = open(
                    filename,
                    "w",
                    encoding="utf-8"
                )
                self._log_thread = threading.Thread(target=self._write_logs,
                                                    name="UDS-LOG", daemon=True)
                self._log_thread.start()
                self.log(f"完整日志文件：{os.path.abspath(filename)}")
            self.log(f"BOOTLOADER_REV=2026-10-21-vector-tx-v4 Python={platform.python_version()} "
                     f"python-can={can.__version__} OS={platform.platform()}")
            self.log("日志说明：TX_QUEUED 表示 Vector 驱动已接受 1 帧；TX_COMPLETED 为驱动报告的发送完成回执，"
                     "均不代表 ECU 已执行 UDS 请求；"
                     "RX_RAW hw_ts 来自驱动，lag 为主机处理延迟估计；文件保存全部 CF。")
            with open(self.bin_file, "rb") as f:
                firmware = f.read()
            fw_size = len(firmware)
            if not fw_size:
                raise ValueError("BIN 文件为空，停止刷写")
            self.log(f"FIRMWARE：path={os.path.abspath(self.bin_file)} size={fw_size} "
                     f"sha256={hashlib.sha256(firmware).hexdigest()}")
            # 创建 CAN
            self.create_bus()
            self.log("接收方式：后台持续收帧；严格流控和事务校验；文件日志异步写入")
            self.stage_signal.emit(
                "进入 Extended Session"
            )
            self.send_request([0x10, 0x03], retries=2)
            self.stage_signal.emit(
                "进入 Programming Session"
            )
            self.send_request([0x10, 0x02], retries=2)
            self.stage_signal.emit(
                "Security Access"
            )
            seed_resp = self.send_request([0x27, 0x01], retries=2)
            if seed_resp is not None and len(seed_resp) >= 6:
                seed = seed_resp[2:6]
            else:
                raise ValueError("SecurityAccess Seed 应答不完整，停止刷写")
            self.log(f"Seed: {self._hex(seed)}")
            key = self.calc_key(seed)
            self.log(f"Key : {self._hex(key)}")
            self.send_request([0x27, 0x02] + key, retries=2)
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
            # 擦除属于有副作用操作：超时后停止，避免 ECU 尚在擦除时再次触发。
            self.send_request(erase_payload)
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
            dl_resp = self.send_request(request_download, retries=2)
            if dl_resp:
                self.log(f"RequestDownload 应答: {self._hex(dl_resp)}")
            max_block = self._parse_download_response(dl_resp)
            if max_block and max_block > 2:
                # maxNumberOfBlockLength 含服务号(0x36)+块序号共 2 字节
                self.block_size = max(1, min(self.TRANSFER_SIZE, max_block - 2))
                self.log(
                    f"ECU 允许的最大块长度: {max_block} 字节 "
                    f"-> 每次传输数据 {self.block_size} 字节"
                )
            else:
                raise ValueError(f"RequestDownload 最大块长度无效: {dl_resp}")
            self.stage_signal.emit(
                "Transfer Data"
            )
            total_blocks = max(
                1,
                (fw_size + self.block_size - 1) // self.block_size
            )
            self.log(
                f"传输参数：块大小 {self.block_size} 字节，"
                f"连续帧间隔 {CF_DELAY_S * 1000:.1f} ms，"
                f"块间隔 {BLOCK_GAP_S * 1000:.0f} ms，"
                f"每块最多重发 {BLOCK_MAX_RETRY} 次"
            )
            offset = 0
            bsc = 1                # 块序号：0x01 起，0xFF 后回到 0x00
            block_no = 0
            retried = 0
            while offset < fw_size:
                chunk = firmware[
                    offset:
                    offset + self.block_size
                ]
                payload = [
                    0x36,
                    bsc
                ] + list(chunk)
                block_no += 1
                self.log(
                    f"-> 第 {block_no}/{total_blocks} 块 "
                    f"({len(chunk)} 字节, 序号 {bsc})"
                )
                acked = False
                for attempt in range(1, BLOCK_MAX_RETRY + 2):
                    try:
                        self.log(f"BLOCK_SEND：block={block_no}/{total_blocks} "
                                 f"offset={offset} size={len(chunk)} BSC=0x{bsc:02X} "
                                 f"attempt={attempt}/{BLOCK_MAX_RETRY + 1}")
                        self.send_request(payload)
                        acked = True
                        break
                    except ResponsePendingTimeout:
                        raise
                    except UDSNegativeResponse as exc:
                        if exc.nrc == 0x73:
                            self.log(f"BLOCK_ABORT：第 {block_no} 块序号错误，"
                                     "无法确认数据已写入，停止刷写，请重新开始")
                        raise
                    except TimeoutError as exc:
                        self.log(f"BLOCK_TIMEOUT：block={block_no} BSC=0x{bsc:02X} "
                                 f"attempt={attempt} reason={exc}")
                    if attempt <= BLOCK_MAX_RETRY:
                        retried += 1
                        self.log(
                            f"  第 {block_no} 块未收到应答"
                            f"（第 {attempt}/{BLOCK_MAX_RETRY + 1} 次），"
                            f"{BLOCK_RETRY_GAP_S * 1000:.0f} ms 后重发同一块"
                        )
                        time.sleep(BLOCK_RETRY_GAP_S)
                    else:
                        self.log(
                            f"  第 {block_no} 块第 {attempt}/{BLOCK_MAX_RETRY + 1} "
                            "次请求仍未收到应答，停止重发"
                        )
                if not acked:
                    raise TimeoutError(f"第 {block_no}/{total_blocks} 块连续 "
                                       f"{BLOCK_MAX_RETRY + 1} 次未获确认，传输中止")
                offset += len(chunk)
                bsc += 1
                if bsc > 0xFF:
                    bsc = 0
                progress = int(
                    offset / fw_size * 99
                )
                self.progress_signal.emit(
                    progress
                )
                time.sleep(BLOCK_GAP_S)
            self.log(
                f"TransferData 完成：共 {block_no} 块，"
                f"重发 {retried} 次，每块均已收到对应 0x76 确认"
            )
            self.stage_signal.emit(
                "Transfer Exit"
            )
            self.send_request([0x37])
            self.stage_signal.emit(
                "ECU Reset"
            )
            # ECU Reset 可能不回应（立即复位），失败不视为刷写失败
            reset_resp = self.send_request([0x11, 0x01], timeout=1.0, required=False)
            if reset_resp is None:
                self.log("RESET_UNCONFIRMED：下载已确认完成；ECU 未应答复位，可能已立即复位，"
                         "请检查设备是否重新上线")
            self.progress_signal.emit(100)
            self.stage_signal.emit(
                "刷写完成"
            )
            success = True
        except Exception as e:
            self.log(f"FLASH_FAILED：{type(e).__name__}: {e}")
            self.stage_signal.emit("刷写失败")
        finally:
            self._stop_rx()
            if self.bus:
                try:
                    self.bus.shutdown()
                except Exception as exc:
                    self.log(f"CAN shutdown 异常: {exc}")
                self.bus = None
            self.log(f"FLASH_RESULT：success={success} elapsed="
                     f"{time.perf_counter() - self._started_at:.3f}s stats={self.stats} "
                     f"log_backlog={self._log_queue.qsize()} "
                     f"chip_state={self._transport.last_state if self._transport is not None else 'unavailable'}")
            self._close_log()
            # 总线及接收线程释放后再通知 UI，避免重新初始化 CAN 时竞争。
            self.finished_signal.emit(success)
