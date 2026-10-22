"""Run the installed python-can Vector packing/send code with a fake XL DLL.

No hardware, real driver functions, or application mappings are opened/changed.
"""
import ctypes
from pathlib import Path
import queue
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import can
from can.interfaces.vector import VectorBus
from can.interfaces.vector import xlclass, xldefine
from can.interfaces.vector.exceptions import VectorOperationError
from PySide6.QtCore import Qt
from uds.uds_flasher import UDSFlasher
from uds.vector_transport import VectorTransport


class VectorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.calls = []
        self.accepted = 1
        self.error = None
        self.settings_values = {'can_interface': 'vector_vn1630a'}
        settings = Mock()
        settings.value.side_effect = lambda key, default=None: self.settings_values.get(key, default)
        item = patch('uds.uds_flasher.QSettings', return_value=settings)
        item.start()
        self.addCleanup(item.stop)
        # Deliberately skip __init__: every XL entry point is replaced by a
        # Python fake, while the actual python-can send/packing methods run.
        self.bus = object.__new__(VectorBus)
        self.bus._is_shutdown = True
        self.bus._can_protocol = can.CanProtocol.CAN_20
        self.bus._filters = None
        self.bus._time_offset = 0
        self.bus.mask = 1 << 7
        self.bus.channel_masks = {0: 1 << 7}
        self.bus.index_to_channel = {7: 0}
        self.bus.permission_mask = 1 << 7
        self.bus.channel_info = 'Application VectorTest: CAN 1'
        self.bus.port_handle = ctypes.c_long(100)
        self.bus.xldriver = SimpleNamespace(
            xlCanTransmit=self.transmit,
            xlCanTransmitEx=self.transmit_fd,
            xlCanRequestChipState=Mock(),
        )
        self.transport = VectorTransport(self.bus, lambda line: self.logs.append(line))
        self.flasher = UDSFlasher('unused.bin')
        self.flasher.bus = self.bus
        self.flasher._transport = self.transport
        self.flasher.log_signal.connect(self.logs.append)

    def transmit(self, port, mask, count, events):
        msg = events[0].tagData.msg
        self.calls.append((port.value, mask, msg.id, msg.dlc, msg.flags, bytes(msg.data)))
        if self.error:
            raise self.error
        count.value = self.accepted

    def transmit_fd(self, port, mask, requested, sent, events):
        msg = events[0].tagData.canMsg
        self.calls.append((port.value, mask, msg.canId, msg.dlc, msg.msgFlags, bytes(msg.data)))
        sent.value = self.accepted

    @staticmethod
    def config(hw_type=57, output_mode=1):
        active = SimpleNamespace(bitrate=1000000, output_mode=output_mode)
        return SimpleNamespace(name='Fake VN', serial_number=12345, hw_type=hw_type,
                               hw_index=0, hw_channel=1, channel_index=7,
                               is_on_bus=True, transceiver_name='Fake CAN',
                               bus_params=SimpleNamespace(can=active, canfd=active))

    def test_initial_request_reaches_xl_with_exact_bytes_and_mask(self):
        self.flasher.uds_send([0x10, 0x03])
        self.assertEqual(self.calls, [(100, 128, 0x4E0, 8, 0,
                                     bytes.fromhex('02 10 03 AA AA AA AA AA'))])
        self.assertEqual(self.flasher.stats['tx'], 1)
        self.assertTrue(any('TX_QUEUED' in line for line in self.logs))

    def test_zero_accepted_is_failure_without_success_log_or_retry(self):
        self.accepted = 0
        with self.assertRaisesRegex(can.CanOperationError, 'accepted=0'):
            self.flasher.uds_send([0x10, 0x03])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.flasher.stats['tx'], 0)
        self.assertEqual(self.flasher.stats['tx_failed'], 1)
        self.assertFalse(any('TX_QUEUED' in line for line in self.logs))

    def test_transfer_block_reaches_xl_without_missing_or_reordered_bytes(self):
        payload = [0x36, 0x77] + list(bytes(range(256)) * 8)
        with patch.object(self.flasher, 'pop_flow_control', return_value=(0, 0)), \
                patch('uds.uds_flasher.CF_DELAY_S', 0):
            self.flasher.send_multi_frame(payload)
        self.assertEqual(len(self.calls), 293)
        frames = [list(call[-1]) for call in self.calls]
        self.assertEqual(frames[0][:4], [0x18, 0x02, 0x36, 0x77])
        restored = frames[0][2:]
        for index, frame in enumerate(frames[1:], 1):
            self.assertEqual(frame[0], 0x20 | (index & 15))
            restored.extend(frame[1:])
        self.assertEqual(restored[:len(payload)], payload)
        self.assertTrue(all(call[1:5] == (128, 0x4E0, 8, 0) for call in self.calls))

    def test_real_vector_receive_decoder_preserves_tx_completion_flag(self):
        event = xlclass.XLevent()
        event.tag = xldefine.XL_EventTags.XL_RECEIVE_MSG
        event.chanIndex = 7
        event.tagData.msg.id = 0x4E0
        event.tagData.msg.dlc = 8
        event.tagData.msg.flags = xldefine.XL_MessageFlags.XL_CAN_MSG_FLAG_TX_COMPLETED
        event.tagData.msg.data = tuple(bytes.fromhex('02 10 03 AA AA AA AA AA'))

        def receive(port, count, output):
            ctypes.memmove(ctypes.addressof(output), ctypes.addressof(event), ctypes.sizeof(event))

        self.bus._time_offset = 0
        self.bus.xldriver.xlReceive = receive
        message = self.bus._recv_can()
        self.assertFalse(message.is_rx)
        self.assertEqual(message.channel, 0)
        self.flasher._handle_frame(message)
        self.assertEqual(self.flasher.stats['tx_completed'], 1)
        self.assertEqual(self.flasher._msgs, [])

    def test_driver_exception_propagates_without_success_log(self):
        self.error = can.CanOperationError('XL_ERR_QUEUE_IS_FULL')
        with self.assertRaisesRegex(can.CanOperationError, 'QUEUE_IS_FULL'):
            self.flasher.uds_send([0x10, 0x03])
        self.assertEqual(self.flasher.stats['tx'], 0)
        self.assertFalse(any('TX_QUEUED' in line for line in self.logs))

    def test_invalid_classic_frame_never_calls_driver(self):
        with self.assertRaises(ValueError):
            self.flasher.send_can(list(range(9)))
        self.assertEqual(self.calls, [])

    def test_fd_uses_xl_transmit_ex_and_checks_accepted_count(self):
        self.bus._can_protocol = can.CanProtocol.CAN_FD
        self.flasher.fd = True
        self.flasher.uds_send([0x10, 0x03])
        self.assertEqual(self.calls[0][2:4], (0x4E0, 8))
        self.assertEqual(self.calls[0][-1][:8], bytes.fromhex('02 10 03 AA AA AA AA AA'))
        self.accepted = 0
        with self.assertRaisesRegex(can.CanOperationError, 'accepted=0'):
            self.flasher.uds_send([0x10, 0x03])

    def test_physical_mapping_is_reported(self):
        with patch('uds.vector_transport.get_channel_configs', return_value=[self.config()]):
            self.transport.describe()
        text = '\n'.join(self.logs)
        for field in ('serial=12345', 'hw_channel=1', 'physical_port=2', 'global_index=7',
                      'init_access=0x80'):
            self.assertIn(field, text)

    def test_virtual_channel_is_rejected(self):
        with patch('uds.vector_transport.get_channel_configs', return_value=[self.config(hw_type=1)]):
            with self.assertRaisesRegex(can.CanInitializationError, '虚拟通道'):
                self.transport.describe()

    def test_silent_and_tx_off_modes_are_rejected(self):
        for output in (0, 2, 3):
            with self.subTest(output=output), patch('uds.vector_transport.get_channel_configs',
                                                  return_value=[self.config(output_mode=output)]):
                with self.assertRaisesRegex(can.CanInitializationError, 'NORMAL'):
                    self.transport.describe()

    def test_shared_initialization_access_is_reported(self):
        self.bus.permission_mask = 0
        with patch('uds.vector_transport.get_channel_configs', return_value=[self.config()]):
            self.transport.describe()
        self.assertTrue(any('VECTOR_SHARED_CHANNEL' in line for line in self.logs))

    def test_bus_off_event_stops_send_and_response_wait_even_after_recovery(self):
        event = xlclass.XLevent()
        event.tag = xldefine.XL_EventTags.XL_CHIP_STATE
        event.chanIndex = 7
        event.tagData.chipState.busStatus = xldefine.XL_BusStatus.XL_CHIPSTAT_BUSOFF
        event.tagData.chipState.txErrorCounter = 255
        self.bus.handle_can_event(event)
        event.tagData.chipState.busStatus = xldefine.XL_BusStatus.XL_CHIPSTAT_ERROR_ACTIVE
        self.bus.handle_can_event(event)
        with self.assertRaisesRegex(can.CanOperationError, 'BUS_OFF'):
            self.flasher.uds_send([0x10, 0x03])
        with self.assertRaisesRegex(can.CanOperationError, 'BUS_OFF'):
            self.flasher.recv_response([0x10, 0x03])
        self.assertEqual(self.calls, [])
        self.assertTrue(any('tx_errors=255' in line for line in self.logs))

    def test_tx_completion_is_counted_but_cannot_confirm_uds_request(self):
        message = can.Message(arbitration_id=0x4E0, is_extended_id=False,
                              is_rx=False, data=bytes.fromhex('02 10 03 AA AA AA AA AA'))
        self.flasher._handle_frame(message)
        self.assertEqual(self.flasher.stats['tx_completed'], 1)
        self.assertEqual(self.flasher._msgs, [])
        self.assertEqual(self.flasher._fcs, [])
        self.assertEqual(self.flasher._echo_count, 0)

    def test_error_flagged_tx_receipt_is_not_counted_as_completed(self):
        self.flasher._handle_frame(can.Message(arbitration_id=0x4E0,
                                              is_rx=False, is_error_frame=True))
        self.assertEqual(self.flasher.stats['tx_completed'], 0)

    def test_canfd_error_and_chip_state_events_are_logged(self):
        event = xlclass.XLcanRxEvent()
        event.tag = xldefine.XL_CANFD_RX_EventTags.XL_CAN_EV_TAG_TX_ERROR
        event.tagData.canError.errorCode = 6
        self.bus.handle_canfd_event(event)
        self.assertTrue(any('error_code=6' in line for line in self.logs))
        event.tag = xldefine.XL_CANFD_RX_EventTags.XL_CAN_EV_TAG_CHIP_STATE
        event.tagData.canChipState.busStatus = xldefine.XL_BusStatus.XL_CHIPSTAT_BUSOFF
        self.bus.handle_canfd_event(event)
        with self.assertRaises(can.CanOperationError):
            self.transport.check_state()

    def test_create_bus_enables_receipts_without_hidden_config_or_broad_filter(self):
        fake_settings = Mock()
        fake_settings.value.return_value = 'vector'
        with patch('uds.uds_flasher.QSettings', return_value=fake_settings), \
                patch('can.interface.Bus', return_value=self.bus) as factory, \
                patch('uds.vector_transport.get_channel_configs', return_value=[self.config()]), \
                patch.object(self.flasher, '_start_rx'):
            self.flasher.create_bus()
        kwargs = factory.call_args.kwargs
        self.assertIs(kwargs['receive_own_messages'], True)
        self.assertIs(kwargs['listen_only'], False)
        self.assertIs(kwargs['ignore_config'], True)
        filters = kwargs['can_filters']
        self.assertEqual(len(filters), 1)
        accepted_ids = [i for i in range(2048) if i & filters[0]['can_mask'] == filters[0]['can_id']]
        self.assertEqual(accepted_ids, [0x4C0, 0x4D0, 0x4E0, 0x4F0])
        self.bus.xldriver.xlCanRequestChipState.assert_called_once()

    def test_pcan_setting_cannot_silently_send_to_vector(self):
        self.settings_values['can_interface'] = 'pcan'
        flasher = UDSFlasher('unused.bin')
        with patch('can.interface.Bus') as factory:
            with self.assertRaisesRegex(ValueError, 'pcan'):
                flasher.create_bus()
        factory.assert_not_called()

    def test_vn1610_uses_saved_app_channel_and_bitrate_without_fixed_serial(self):
        cfg = self.config(hw_type=55)
        cfg.serial_number = 98765
        cfg.bus_params.can.bitrate = 500000
        self.settings_values.update(can_interface='vector_vn1610', app_name='BMS1610',
                                    channel=1, arb_bitrate=500000)
        flasher = UDSFlasher('unused.bin', fd=True)
        with patch('can.interface.Bus', return_value=self.bus) as factory, \
                patch('uds.vector_transport.get_channel_configs', return_value=[cfg]), \
                patch.object(flasher, '_start_rx'):
            flasher.create_bus()
        kwargs = factory.call_args.kwargs
        self.assertEqual((kwargs['app_name'], kwargs['channel'], kwargs['bitrate'], kwargs['fd']),
                         ('BMS1610', 1, 500000, False))
        self.assertNotIn('serial', kwargs)
        self.assertTrue(kwargs['ignore_config'])
        self.assertNotIn('data_bitrate', kwargs)

    def test_configured_model_and_bitrate_reject_wrong_vhm_mapping(self):
        for field, wrong in (('hw_type', 57), ('hw_type', 1), ('bitrate', 500000)):
            cfg = self.config(hw_type=55)
            cfg.serial_number, cfg.hw_channel = 26774, 0
            if field == 'bitrate':
                cfg.bus_params.can.bitrate = wrong
            else:
                setattr(cfg, field, wrong)
            with self.subTest(field=field), \
                    patch('uds.vector_transport.get_channel_configs', return_value=[cfg]):
                with self.assertRaises(can.CanInitializationError):
                    self.transport.describe(expected_hw_type=55, expected_bitrate=1000000)
        self.assertEqual(self.calls, [])

    def test_vn1610_profile_requires_initialization_permission(self):
        cfg = self.config(hw_type=55)
        cfg.serial_number, cfg.hw_channel = 26774, 0
        self.bus.permission_mask = 0
        with patch('uds.vector_transport.get_channel_configs', return_value=[cfg]):
            with self.assertRaisesRegex(can.CanInitializationError, '共享'):
                self.transport.describe(expected_hw_type=55, require_init_access=True)

    def test_disconnected_vn1610_never_falls_back_to_application_or_other_card(self):
        self.settings_values.update(can_interface='vector_vn1610', app_name='BMS1610')
        flasher = UDSFlasher('unused.bin')
        with patch('can.interface.Bus', side_effect=can.CanInitializationError('not found')) as factory:
            with self.assertRaises(can.CanInitializationError):
                flasher.create_bus()
        factory.assert_called_once()
        self.assertEqual(factory.call_args.kwargs['app_name'], 'BMS1610')
        self.assertNotIn('serial', factory.call_args.kwargs)
        self.assertIsNone(flasher.bus)

    def test_state_events_before_response_are_drained_without_waiting(self):
        state = xlclass.XLevent()
        state.tag = xldefine.XL_EventTags.XL_CHIP_STATE
        state.tagData.chipState.busStatus = xldefine.XL_BusStatus.XL_CHIPSTAT_ERROR_ACTIVE
        response = xlclass.XLevent()
        response.tag = xldefine.XL_EventTags.XL_RECEIVE_MSG
        response.tagData.msg.id = 0x4D0
        response.tagData.msg.dlc = 8
        response.tagData.msg.data = tuple(bytes.fromhex('06 50 03 00 32 00 C8 FF'))
        events = iter([state] * 32 + [response])

        def receive(port, count, output):
            event = next(events)
            ctypes.memmove(ctypes.addressof(output), ctypes.addressof(event), ctypes.sizeof(event))

        self.bus.xldriver.xlReceive = receive
        with patch.object(self.transport, '_wait_for_rx', side_effect=AssertionError('queued event must not wait')):
            result = self.transport.recv(0.5)
        self.assertEqual(result.arbitration_id, 0x4D0)
        self.assertEqual(bytes(result.data), bytes.fromhex('06 50 03 00 32 00 C8 FF'))

    def test_empty_receive_queue_waits_then_receives_fd_tx_receipt(self):
        self.bus._can_protocol = can.CanProtocol.CAN_FD
        receipt = can.Message(arbitration_id=0x4E0, is_extended_id=False, is_rx=False)
        empty = VectorOperationError(10, 'XL_ERR_QUEUE_IS_EMPTY', 'xlCanReceive')
        with patch.object(self.bus, '_recv_canfd', side_effect=[empty, receipt]), \
                patch.object(self.transport, '_wait_for_rx') as wait:
            self.assertIs(self.transport.recv(), receipt)
        wait.assert_called_once()

    def test_receive_timeout_and_driver_errors_remain_distinct(self):
        empty = VectorOperationError(10, 'XL_ERR_QUEUE_IS_EMPTY', 'xlReceive')
        with patch.object(self.bus, '_recv_can', side_effect=empty), \
                patch.object(self.transport, '_wait_for_rx') as wait:
            self.assertIsNone(self.transport.recv(0))
        wait.assert_not_called()
        failure = VectorOperationError(129, 'XL_ERR_HW_NOT_PRESENT', 'xlReceive')
        with patch.object(self.bus, '_recv_can', side_effect=failure):
            with self.assertRaises(VectorOperationError):
                self.transport.recv()

    def test_full_flash_uses_native_xl_packing_and_receive_with_state_event_backlog(self):
        from test_bootloader_protocol import SimulatedECU
        with tempfile.TemporaryDirectory() as directory:
            firmware = bytes(range(256)) * 32
            path = Path(directory) / 'firmware.bin'
            path.write_bytes(firmware)
            self.settings_values['can_interface'] = 'vector_vn1610'
            flasher = UDSFlasher(str(path))
            ecu = SimulatedECU(flasher, threaded=True, bs=8, multi_response=True)
            cfg = self.config(hw_type=55)
            cfg.serial_number, cfg.hw_channel = 26774, 0
            pending = []

            def transmit(port, mask, count, events):
                self.transmit(port, mask, count, events)
                data = list(events[0].tagData.msg.data)
                ecu.rx_queue.put(can.Message(arbitration_id=0x4E0, is_extended_id=False,
                                             is_rx=False, timestamp=time.time(), data=data))
                ecu.send(can.Message(arbitration_id=0x4E0, is_extended_id=False, data=data))

            def receive(port, count, output):
                if not pending:
                    try:
                        pending.append(ecu.rx_queue.get_nowait())
                    except queue.Empty:
                        raise VectorOperationError(10, 'XL_ERR_QUEUE_IS_EMPTY', 'xlReceive') from None
                    output.tag = xldefine.XL_EventTags.XL_CHIP_STATE
                    output.tagData.chipState.busStatus = xldefine.XL_BusStatus.XL_CHIPSTAT_ERROR_ACTIVE
                    return
                message = pending.pop()
                output.tag = xldefine.XL_EventTags.XL_RECEIVE_MSG
                output.timeStamp = int(message.timestamp * 1e9)
                output.tagData.msg.id = message.arbitration_id
                output.tagData.msg.dlc = message.dlc
                output.tagData.msg.flags = (0 if message.is_rx else
                                           xldefine.XL_MessageFlags.XL_CAN_MSG_FLAG_TX_COMPLETED)
                output.tagData.msg.data = tuple(message.data)

            self.bus.xldriver.xlCanTransmit = transmit
            self.bus.xldriver.xlReceive = receive
            self.bus.shutdown = Mock()
            self.bus.event_handle = ctypes.c_void_p(0)
            results = []
            flasher.finished_signal.connect(results.append, Qt.DirectConnection)
            with patch('can.interface.Bus', return_value=self.bus), \
                    patch('uds.vector_transport.get_channel_configs', return_value=[cfg]), \
                    patch.object(VectorTransport, '_wait_for_rx', side_effect=lambda s: time.sleep(0.001)), \
                    patch('uds.uds_flasher.CF_DELAY_S', 0):
                flasher.flash()
            self.assertEqual(results, [True])
            self.assertEqual(ecu.written, firmware)
            self.assertEqual(flasher.stats['tx'], len(self.calls))
            self.assertEqual(flasher.stats['tx_failed'], 0)
            self.assertEqual(flasher.stats['driver_errors'], 0)
            self.assertGreater(flasher.stats['tx_completed'], 1000)
            self.bus.shutdown.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
