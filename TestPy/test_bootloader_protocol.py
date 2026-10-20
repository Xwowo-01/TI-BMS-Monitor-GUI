"""Bootloader regression tests. Uses simulated CAN only; never opens hardware.

Run: python -B -m unittest discover -s TestPy -p test_bootloader_protocol.py -v
"""
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import can
from PySide6.QtCore import QCoreApplication, Qt
import uds.uds_flasher as impl


def frames(payload):
    if len(payload) <= 7:
        return [[len(payload)] + payload + [0xFF] * (7 - len(payload))]
    result = [[0x10 | (len(payload) >> 8), len(payload) & 255] + payload[:6]]
    for index, offset in enumerate(range(6, len(payload), 7), 1):
        frame = [0x20 | (index & 15)] + payload[offset:offset + 7]
        result.append(frame + [0xFF] * (8 - len(frame)))
    return result


class SimulatedECU:
    def __init__(self, flasher, *, no_fc=False, bs=0, wait_only=False,
                 wait_then_cts=False, missing_next_fc=False, overflow=False,
                 stmin=0, drop_data=False, drop_ack=False, retry_nrc73=False,
                 missing_exit=False, reset_nrc=False, pending=False,
                 pending_only=False, duplicate=False, threaded=False,
                 multi_response=False, max_block=0x0802, old_ack=False):
        self.flasher = flasher
        self.options = locals().copy()
        self.tx = []
        self.requests = []
        self.rx_queue = queue.Queue()
        self.ff = None
        self.response_cfs = []
        self.written = bytearray()
        self.expected = 1
        self.last_block = None
        self.transfer_attempts = 0
        self.closed = False

    def receive(self, data, timestamp=None):
        message = can.Message(arbitration_id=impl.UDSFlasher.RX_ID,
                              data=data, is_extended_id=False,
                              timestamp=time.time() if timestamp is None else timestamp,
                              is_fd=self.flasher.fd)
        if self.options['threaded']:
            self.rx_queue.put(message)
        else:
            self.flasher._handle_frame(message)

    def recv(self, timeout):
        try:
            return self.rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def send_fc(self):
        if self.options['no_fc']:
            return
        if self.options['wait_only'] or self.options['wait_then_cts']:
            self.receive([0x31, 0, 0] + [0xFF] * 5)
            if self.options['wait_only']:
                return
        self.receive([0x32 if self.options['overflow'] else 0x30,
                      self.options['bs'], self.options['stmin']] + [0xFF] * 5)

    def send(self, message):
        data = list(message.data)
        self.tx.append(data)
        kind = data[0] & 0xF0
        if kind == 0:
            self.answer(data[1:1 + data[0]])
        elif kind == 0x10:
            self.ff = {'total': ((data[0] & 15) << 8) | data[1],
                       'data': data[2:], 'sn': 1, 'count': 0}
            self.send_fc()
        elif kind == 0x20:
            if self.ff is None or (data[0] & 15) != self.ff['sn']:
                raise AssertionError('tester sent an invalid CF sequence')
            self.ff['data'].extend(data[1:])
            self.ff['sn'] = (self.ff['sn'] + 1) & 15
            self.ff['count'] += 1
            if len(self.ff['data']) >= self.ff['total']:
                req = self.ff['data'][:self.ff['total']]
                self.ff = None
                self.answer(req)
            elif (self.options['bs'] and self.ff['count'] % self.options['bs'] == 0
                  and not self.options['missing_next_fc']):
                self.send_fc()
        elif kind == 0x30:
            pending, self.response_cfs = self.response_cfs, []
            for frame in pending:
                self.receive(frame)

    def reply(self, payload):
        encoded = frames(payload)
        if len(encoded) > 1:
            self.response_cfs = encoded[1:]
        self.receive(encoded[0])

    def answer(self, request):
        self.requests.append(request)
        sid = request[0]
        if sid == 0x10:
            response = [0x50, request[1], 0, 0, 0, 0]
        elif sid == 0x27:
            response = [0x67, request[1]] + ([1, 2, 3, 4] if request[1] == 1 else [])
        elif sid == 0x31:
            if self.options['pending'] or self.options['pending_only']:
                self.reply([0x7F, sid, 0x78])
                if self.options['pending_only']:
                    return
            response = [0x71, 1, 0xFF, 0, 0]
            if self.options['multi_response']:
                response.extend([1, 2, 3, 4, 5])
        elif sid == 0x34:
            size = self.options['max_block']
            response = [0x74, 0x20, size >> 8, size & 255]
        elif sid == 0x36:
            self.transfer_attempts += 1
            if self.options['old_ack']:
                self.receive(frames([0x76, request[1]])[0], timestamp=time.time() - 5)
                return
            if self.transfer_attempts == 1 and (self.options['drop_data']
                                                 or self.options['retry_nrc73']):
                return
            if self.options['retry_nrc73']:
                self.reply([0x7F, 0x36, 0x73])
                return
            if self.last_block == bytes(request):
                self.reply([0x76, request[1]])  # 上一块重发：确认，但不能重复写入
                return
            if request[1] != self.expected:
                self.reply([0x7F, 0x36, 0x73])
                return
            self.written.extend(request[2:])
            self.last_block = bytes(request)
            self.expected = (self.expected + 1) & 255
            if self.options['drop_ack'] and self.transfer_attempts == 1:
                return
            response = [0x76, request[1]]
        elif sid == 0x37:
            if self.options['missing_exit']:
                return
            response = [0x77]
        elif sid == 0x11:
            response = [0x7F, sid, 0x22] if self.options['reset_nrc'] else [0x51, 1]
        else:
            raise AssertionError(request)
        self.reply(response)
        if self.options['duplicate']:
            self.reply(response)

    def shutdown(self):
        self.closed = True


class BootloaderProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for key, value in dict(RESP_TIMEOUT=0.015, FC_WAIT_TIMEOUT=0.015,
                               FC_MAX_WAIT_S=0.06, RESPONSE_MAX_WAIT_S=0.08,
                               CF_DELAY_S=0, BLOCK_GAP_S=0,
                               BLOCK_RETRY_GAP_S=0).items():
            item = patch.object(impl, key, value)
            item.start()
            self.addCleanup(item.stop)
        self.firmware = bytes(range(256)) * 2
        self.bin_path = Path(self.temp.name) / 'firmware.bin'
        self.bin_path.write_bytes(self.firmware)

    def make(self, **options):
        flasher = impl.UDSFlasher(str(self.bin_path), fd=False)
        bus = SimulatedECU(flasher, **options)
        flasher.bus = bus
        flasher.create_bus = lambda: self.start(flasher, bus, options.get('threaded'))
        self.addCleanup(flasher._stop_rx)
        return flasher, bus

    @staticmethod
    def start(flasher, bus, threaded):
        flasher.bus = bus
        if threaded:
            flasher._start_rx()

    def flash(self, **options):
        flasher, bus = self.make(**options)
        result = []
        flasher.finished_signal.connect(result.append, Qt.DirectConnection)
        flasher.flash()
        self.assertTrue(bus.closed)
        return flasher, bus, result

    def test_missing_initial_fc_sends_no_cf(self):
        flasher, bus = self.make(no_fc=True)
        with self.assertRaisesRegex(TimeoutError, 'FlowControl'):
            flasher.send_request([0x36, 1] + list(range(25)))
        self.assertEqual(len(bus.tx), 1)

    def test_wait_without_cts_sends_no_cf(self):
        flasher, bus = self.make(wait_only=True)
        with self.assertRaises(TimeoutError):
            flasher.send_request([0x36, 1] + list(range(25)))
        self.assertEqual(len(bus.tx), 1)

    def test_wait_then_cts(self):
        flasher, bus = self.make(wait_then_cts=True)
        self.assertEqual(flasher.send_request([0x36, 1] + list(range(25))), [0x76, 1])
        self.assertEqual(bus.written, bytes(range(25)))

    def test_missing_next_fc_stops_at_bs(self):
        flasher, bus = self.make(bs=1, missing_next_fc=True)
        with self.assertRaises(TimeoutError):
            flasher.send_request([0x36, 1] + list(range(25)))
        self.assertEqual(sum(frame[0] & 0xF0 == 0x20 for frame in bus.tx), 1)

    def test_multiple_bs_windows(self):
        flasher, bus = self.make(bs=2)
        flasher.send_request([0x36, 1] + list(range(60)))
        self.assertEqual(bus.written, bytes(range(60)))

    def test_overflow_aborts(self):
        flasher, bus = self.make(overflow=True)
        with self.assertRaisesRegex(RuntimeError, 'OVFLW'):
            flasher.send_request([0x36, 1] + list(range(25)))
        self.assertEqual(len(bus.tx), 1)

    def test_reserved_stmin_rejected(self):
        flasher, bus = self.make(stmin=0x80)
        with self.assertRaises(ValueError):
            flasher.send_request([0x36, 1] + list(range(25)))
        self.assertEqual(len(bus.tx), 1)

    def test_stmin_spacing(self):
        flasher, bus = self.make(stmin=2)
        flasher.send_request([0x36, 1] + list(range(25)))
        self.assertGreaterEqual(flasher.stats['max_cf_gap_ms'], 2)

    def test_cached_ack_cannot_confirm_new_request(self):
        flasher, _ = self.make(drop_data=True)
        flasher._push_msg([0x76, 1])
        with self.assertRaises(TimeoutError):
            flasher.send_request([0x36, 1] + list(range(25)))

    def test_hardware_timestamp_rejects_driver_backlog(self):
        flasher, _ = self.make(old_ack=True)
        with self.assertRaises(TimeoutError):
            flasher.send_request([0x36, 1] + list(range(25)))

    def test_response_match_requires_bsc_and_routine_id(self):
        self.assertFalse(impl.UDSFlasher._matches([0x76], [0x36, 1]))
        self.assertFalse(impl.UDSFlasher._matches([0x76, 2], [0x36, 1]))
        self.assertFalse(impl.UDSFlasher._matches([0x71, 1, 1, 2], [0x31, 1, 255, 0]))

    def test_pending_waits_for_final_response(self):
        flasher, bus = self.make(pending=True)
        self.assertEqual(flasher.send_request([0x31, 1, 255, 0]), [0x71, 1, 255, 0, 0])
        self.assertEqual(len(bus.requests), 1)

    def test_pending_timeout_is_not_retried(self):
        flasher, bus = self.make(pending_only=True)
        with self.assertRaises(impl.ResponsePendingTimeout):
            flasher.send_request([0x31, 1, 255, 0], retries=3)
        self.assertEqual(len(bus.requests), 1)

    def test_continuous_pending_has_total_limit(self):
        flasher, _ = self.make()
        with patch.object(flasher, '_take', return_value=([0x7F, 0x31, 0x78], None)):
            with self.assertRaises(impl.ResponsePendingTimeout):
                flasher.recv_response([0x31, 1, 255, 0])

    def test_normal_flash_with_duplicate_responses(self):
        _, bus, result = self.flash(duplicate=True)
        self.assertEqual(result, [True])
        self.assertEqual(bus.written, self.firmware)

    def test_background_receiver_and_multiframe_response(self):
        _, bus, result = self.flash(threaded=True, multi_response=True)
        self.assertEqual(result, [True])
        self.assertEqual(bus.written, self.firmware)

    def test_lost_data_retries_identical_block(self):
        _, bus, result = self.flash(drop_data=True)
        self.assertEqual(result, [True])
        self.assertEqual(bus.written, self.firmware)
        blocks = [r for r in bus.requests if r[0] == 0x36]
        self.assertEqual(blocks[0], blocks[1])

    def test_lost_ack_retries_without_duplicate_write(self):
        _, bus, result = self.flash(drop_ack=True)
        self.assertEqual(result, [True])
        self.assertEqual(bus.written, self.firmware)
        self.assertEqual(bus.transfer_attempts, 2)

    def test_retry_nrc73_must_not_skip_block(self):
        _, bus, result = self.flash(retry_nrc73=True)
        self.assertEqual(result, [False])
        self.assertEqual(bus.written, b'')
        self.assertFalse(any(r[0] in (0x37, 0x11) for r in bus.requests))

    def test_exit_ack_is_required(self):
        _, bus, result = self.flash(missing_exit=True)
        self.assertEqual(result, [False])
        self.assertFalse(any(r[0] == 0x11 for r in bus.requests))

    def test_reset_negative_response_is_failure(self):
        _, _, result = self.flash(reset_nrc=True)
        self.assertEqual(result, [False])

    def test_empty_firmware_never_opens_bus(self):
        self.bin_path.write_bytes(b'')
        flasher, bus = self.make()
        with patch.object(flasher, 'create_bus') as create:
            flasher.flash()
        create.assert_not_called()
        self.assertEqual(bus.tx, [])

    def test_block_counter_rollover_and_integrity(self):
        flasher, bus = self.make(max_block=18)
        firmware = bytes(range(256)) * 17
        self.bin_path.write_bytes(firmware)
        result = []
        flasher.finished_signal.connect(result.append, Qt.DirectConnection)
        flasher.flash()
        self.assertEqual(result, [True])
        blocks = [r[1] for r in bus.requests if r[0] == 0x36]
        self.assertEqual(blocks[254:258], [255, 0, 1, 2])
        self.assertEqual(bus.written, firmware)

    def test_bad_download_limit_aborts(self):
        _, bus, result = self.flash(max_block=2)
        self.assertEqual(result, [False])
        self.assertEqual(bus.transfer_attempts, 0)

    def test_rx_sequence_error_aborts_reassembly(self):
        flasher, bus = self.make()
        bus.receive([0x10, 10, 0x71, 1, 255, 0, 0, 0])
        with self.assertRaisesRegex(ValueError, '序号'):
            bus.receive([0x22] + [0] * 7)
        self.assertIsNone(flasher._ff)

    def test_driver_error_aborts_wait(self):
        flasher, bus = self.make()
        bus.recv = lambda timeout: (_ for _ in ()).throw(can.CanError('queue overrun'))
        flasher._start_rx()
        flasher._rx_thread.join(timeout=1)
        with self.assertRaisesRegex(RuntimeError, 'queue overrun'):
            flasher.recv_response([0x10, 3])
        self.assertEqual(flasher.stats['driver_errors'], 1)

    def test_blocked_disk_writer_does_not_block_receiver(self):
        flasher, bus = self.make()
        entered, release = threading.Event(), threading.Event()

        class BlockedFile:
            def write(self, text):
                entered.set()
                if not release.wait(timeout=2):
                    raise TimeoutError('test writer was not released')

            def flush(self):
                pass

            def close(self):
                pass

        flasher.log_file = BlockedFile()
        flasher._log_thread = threading.Thread(target=flasher._write_logs, daemon=True)
        flasher._log_thread.start()
        try:
            flasher.log('block the disk writer', show=False)
            self.assertTrue(entered.wait(timeout=1))
            bus.receive(frames([0x76, 1])[0])
            self.assertEqual(flasher._msgs[-1][1], [0x76, 1])
            self.assertFalse(release.is_set())
        finally:
            release.set()
            flasher._close_log()

    def test_full_file_log_and_cleanup_before_finished_signal(self):
        self.bin_path.write_bytes(bytes(range(256)) * 8)
        flasher, bus = self.make()
        flasher.save_log = True
        result = []
        flasher.finished_signal.connect(
            lambda ok: result.append((ok, bus.closed, flasher.log_file is None)),
            Qt.DirectConnection)
        previous = os.getcwd()
        try:
            os.chdir(self.temp.name)
            flasher.flash()
        finally:
            os.chdir(previous)
        self.assertEqual(result, [(True, True, True)])
        log = next(Path(self.temp.name).glob('canlog_*.txt')).read_text(encoding='utf-8')
        cf_lines = [line for line in log.splitlines()
                    if 'TX_QUEUED' in line and '[CF=' in line and 'SID=0x36' in line]
        self.assertEqual(len(cf_lines), 292)
        self.assertIn('CF=292/292', cf_lines[-1])
        for field in ('hw_ts=', 'lag=', 'BSC=0x01', 'call_gap=', 'send_call=',
                      'sha256=', 'BOOTLOADER_REV=', 'FLASH_RESULT', 'FC_CTS'):
            self.assertIn(field, log)
        self.assertEqual(bus.written, self.bin_path.read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
