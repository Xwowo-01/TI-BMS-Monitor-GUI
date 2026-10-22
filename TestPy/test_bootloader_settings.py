"""Exercise model selection, persistence and monitor/flash routing without hardware."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from can_config import VECTOR_VN1610, VECTOR_VN1630A, PCAN
from can_receiver import CANReceiver
from language_manager import language_manager
from pages.setting import SettingUI
from pages.bootloader_page import BootloaderPage
from uds.uds_flasher import UDSFlasher
import vector_utils


class CANSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = QSettings(str(Path(self.temp.name) / 'can.ini'), QSettings.IniFormat)
        for module in ('pages.setting', 'pages.bootloader_page', 'uds.uds_flasher'):
            item = patch(module + '.QSettings', return_value=self.settings)
            item.start()
            self.addCleanup(item.stop)
        item = patch('can.interface.Bus', side_effect=AssertionError('GUI must not open hardware'))
        item.start()
        self.addCleanup(item.stop)
        self.page = SettingUI()
        self.addCleanup(self.close_page)

    def close_page(self):
        language_manager.language_changed.disconnect(self.page.switch_language)
        self.page.close()

    def select(self, interface):
        self.page.interface_combo.setCurrentIndex(self.page.interface_combo.findData(interface))

    def test_dropdown_distinguishes_vector_models_and_pcan(self):
        combo = self.page.interface_combo
        self.assertEqual([combo.itemText(i) for i in range(combo.count())],
                         ['Vector VN1630A', 'Vector VN1610', 'PCAN'])
        self.assertEqual(combo.count(), 3)

    def test_apply_vn1610_config_is_persisted_and_shared_with_real_flasher(self):
        self.select(VECTOR_VN1610)
        self.page.app_name_edit.setText('MyBMS1610')
        self.page.channel_edit.setText('1')
        self.page.arb_bitrate_edit.setText('500000')
        self.page.data_bitrate_edit.clear()  # disabled field must not block Classic CAN
        captured = []
        self.page.reconnect_requested.connect(lambda *args: captured.append(args))
        self.page.reconnect_btn.click()
        self.assertEqual(captured, [(VECTOR_VN1610, 'MyBMS1610', 1, 500000, 500000)])
        self.page.load_saved_config()
        self.assertEqual(self.page.interface_combo.currentData(), VECTOR_VN1610)
        flasher = UDSFlasher('unused.bin', fd=True)
        self.assertEqual((flasher.interface, flasher.vector_app_name, flasher.channel,
                          flasher.bitrate, flasher.fd),
                         (VECTOR_VN1610, 'MyBMS1610', 1, 500000, False))
        flash_page = BootloaderPage()
        self.addCleanup(flash_page.close)
        self.assertFalse(hasattr(flash_page, 'vn1610_checkbox'))
        self.assertFalse(flash_page.fd_checkbox.isEnabled())

    def test_switching_models_and_language_preserves_selection_and_parameters(self):
        self.select(VECTOR_VN1610)
        self.page.app_name_edit.setText('RegisteredName')
        self.assertFalse(self.page.data_bitrate_edit.isEnabled())
        self.page.switch_language('en')
        self.assertEqual(self.page.interface_combo.currentData(), VECTOR_VN1610)
        self.select(VECTOR_VN1630A)
        self.assertTrue(self.page.data_bitrate_edit.isEnabled())
        self.assertEqual(self.page.app_name_edit.text(), 'RegisteredName')
        self.select(PCAN)
        self.assertFalse(self.page.app_name_edit.isEnabled())
        self.assertTrue(self.page.data_bitrate_edit.isEnabled())

    def test_legacy_vector_and_saved_pcan_configs_load_without_losing_parameters(self):
        self.settings.setValue('can_interface', 'vector')
        self.settings.setValue('app_name', 'ExistingApplication')
        self.settings.setValue('channel', 2)
        self.page.load_saved_config()
        self.assertEqual(self.page.interface_combo.currentData(), VECTOR_VN1630A)
        self.assertEqual(self.page.app_name_edit.text(), 'ExistingApplication')
        self.assertEqual(self.page.channel_edit.text(), '2')
        self.settings.setValue('can_interface', PCAN)
        self.page.load_saved_config()
        self.assertEqual(self.page.interface_combo.currentData(), PCAN)

    def test_flash_lifecycle_locks_configuration_and_restores_it_on_failure(self):
        from Main import MainWindow
        self.select(VECTOR_VN1610)
        monitor = Mock()
        window = SimpleNamespace(setting_page=self.page, can_receiver=monitor)
        MainWindow.stop_can_for_flash(window)
        self.assertFalse(self.page.interface_combo.isEnabled())
        self.assertFalse(self.page.app_name_edit.isEnabled())
        self.assertFalse(self.page.reconnect_btn.isEnabled())
        monitor.stop.assert_called_once()
        self.assertIsNone(window.can_receiver)
        MainWindow.restart_can_after_flash(window, False)
        self.assertTrue(self.page.interface_combo.isEnabled())
        self.assertTrue(self.page.reconnect_btn.isEnabled())
        self.assertTrue(self.page.app_name_edit.isEnabled())
        self.assertFalse(self.page.data_bitrate_edit.isEnabled())

    def test_missing_vector_app_name_cannot_be_applied(self):
        self.select(VECTOR_VN1610)
        self.page.app_name_edit.clear()
        emitted = Mock()
        self.page.reconnect_requested.connect(emitted)
        self.page.reconnect_btn.click()
        emitted.assert_not_called()
        self.assertIsNone(self.settings.value('can_interface'))


class CANMonitorRoutingTests(unittest.TestCase):
    def make_monitor(self, interface, actual_hw_type):
        bus = Mock(mask=1 << 7)
        cfg = SimpleNamespace(channel_index=7, hw_type=actual_hw_type,
                              name='Fake Vector', serial_number=98765)
        self.bus = bus
        with patch.object(CANReceiver, '_load_dbc'), \
                patch('can.interface.Bus', return_value=bus) as factory, \
                patch('can.Notifier') as notifier, \
                patch('vector_utils.ensure_vector_application') as ensure, \
                patch('can.interfaces.vector.canlib.get_channel_configs', return_value=[cfg]):
            self.factory, self.notifier, self.ensure = factory, notifier, ensure
            return CANReceiver(interface=interface, app_name='MyBMS', channel=1,
                               arb_bitrate=500000, data_bitrate=1000000)

    def test_vn1610_monitor_uses_classic_can_and_eis_frame_is_unchanged(self):
        monitor = self.make_monitor(VECTOR_VN1610, 55)
        self.assertEqual(self.factory.call_args.kwargs['interface'], 'vector')
        self.assertFalse(self.factory.call_args.kwargs['fd'])
        self.ensure.assert_called_once_with('MyBMS', 1, hw_type=55)
        self.assertTrue(monitor.send_message(0x11, [0x80] + [0] * 7))
        message = self.bus.send.call_args.args[0]
        self.assertEqual((message.arbitration_id, bytes(message.data)),
                         (0x11, b'\x80' + b'\x00' * 7))
        self.assertFalse(message.is_fd)
        self.assertFalse(message.is_extended_id)
        monitor.stop()

    def test_vn1630a_monitor_preserves_canfd_initialization(self):
        monitor = self.make_monitor(VECTOR_VN1630A, 57)
        self.assertTrue(self.factory.call_args.kwargs['fd'])
        self.ensure.assert_called_once_with('MyBMS', 1, hw_type=57)
        monitor.stop()

    def test_wrong_model_from_vhm_is_rejected_and_open_bus_is_closed(self):
        with self.assertRaisesRegex(RuntimeError, '型号与 VHM'):
            self.make_monitor(VECTOR_VN1630A, 55)
        self.bus.shutdown.assert_called_once()
        self.notifier.assert_not_called()
        self.bus.send.assert_not_called()

    def test_pcan_still_uses_pcan_driver_and_channel(self):
        monitor = self.make_monitor(PCAN, 55)
        self.assertEqual(self.factory.call_args.kwargs['interface'], 'pcan')
        self.assertEqual(self.factory.call_args.kwargs['channel'], 'PCAN_USBBUS2')
        self.assertTrue(self.factory.call_args.kwargs['fd'])
        self.ensure.assert_not_called()
        monitor.stop()

    def test_auto_registration_does_not_choose_a_different_vector_model(self):
        import can
        from can.interfaces.vector import VectorBus
        with patch('can.detect_available_configs', return_value=[dict(hw_type=57, hw_channel=0)]), \
                patch.object(VectorBus, 'get_application_config', side_effect=can.CanError('missing app')), \
                patch.object(VectorBus, 'set_application_config') as register:
            with self.assertRaisesRegex(RuntimeError, 'hw_type=55'):
                vector_utils.ensure_vector_application('MyBMS', 0, hw_type=55)
        register.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
