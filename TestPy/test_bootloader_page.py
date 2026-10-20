"""Exercise actual Qt button signals and worker threads without CAN hardware."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pages.bootloader_page as module


class FakeFlasher(QObject):
    log_signal = Signal(str)
    progress_signal = Signal(int)
    stage_signal = Signal(str)
    finished_signal = Signal(bool)

    def __init__(self, result=False, release=None):
        super().__init__()
        self.result = result
        self.release = release
        self.started = threading.Event()

    @Slot()
    def flash(self):
        self.started.set()
        if self.release is not None:
            self.release.wait(timeout=2)
        self.finished_signal.emit(self.result)


class BootloaderPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin_file = Path(self.temp.name) / 'firmware.bin'
        self.bin_file.write_bytes(bytes(range(16)))
        self.page = module.BootloaderPage()
        self.addCleanup(self.page.close)
        self.results = []
        self.page.finished_flash.connect(self.results.append)

    def wait_for(self, predicate):
        deadline = time.perf_counter() + 3
        while not predicate() and time.perf_counter() < deadline:
            QTest.qWait(5)
        self.assertTrue(predicate(), 'Qt event loop did not reach the expected state')

    def assert_idle(self):
        self.assertIsNone(self.page._flash_thread)
        self.assertTrue(self.page.start_btn.isEnabled())
        self.assertTrue(self.page.file_btn.isEnabled())
        self.assertTrue(self.page.fd_checkbox.isEnabled())
        self.assertTrue(self.page.log_checkbox.isEnabled())
        self.assertTrue(callable(self.page.thread))
        self.assertEqual(self.page.thread(), QThread.currentThread())

    def test_first_click_without_file_preserves_qobject_thread_method(self):
        self.page.start_btn.click()
        self.assertIn(self.page.current_ui.PLEASE_SELECT_BIN, self.page.log_text.toPlainText())
        self.assertEqual(self.results, [])
        self.assert_idle()

    def test_first_flash_click_and_success_cleanup(self):
        worker = FakeFlasher(result=True)
        self.page.bin_file = str(self.bin_file)
        with patch.object(module, 'UDSFlasher', return_value=worker) as factory:
            self.page.start_btn.click()
            self.wait_for(lambda: len(self.results) == 1)
        factory.assert_called_once_with(str(self.bin_file), False, False)
        self.assertEqual(self.results, [True])
        self.assert_idle()

    def test_running_flash_ignores_second_click(self):
        release = threading.Event()
        worker = FakeFlasher(release=release)
        self.page.bin_file = str(self.bin_file)
        with patch.object(module, 'UDSFlasher', return_value=worker) as factory:
            try:
                self.page.start_btn.click()
                self.wait_for(worker.started.is_set)
                self.assertFalse(self.page.start_btn.isEnabled())
                self.page.start_btn.click()
                self.page.start_flash()  # also reject a direct duplicate invocation
                factory.assert_called_once()
            finally:
                release.set()
                self.wait_for(lambda: len(self.results) == 1)
        self.assert_idle()

    def test_failed_flash_can_be_started_again(self):
        workers = [FakeFlasher(result=False), FakeFlasher(result=True)]
        self.page.bin_file = str(self.bin_file)
        with patch.object(module, 'UDSFlasher', side_effect=workers) as factory:
            self.page.start_btn.click()
            self.wait_for(lambda: len(self.results) == 1)
            self.assert_idle()
            self.page.start_btn.click()
            self.wait_for(lambda: len(self.results) == 2)
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(self.results, [False, True])
        self.assert_idle()

    def test_constructor_failure_restores_controls(self):
        self.page.bin_file = str(self.bin_file)
        with patch.object(module, 'UDSFlasher', side_effect=ValueError('test setup error')):
            self.page.start_btn.click()
        self.assertEqual(self.results, [False])
        self.assertIn('test setup error', self.page.log_text.toPlainText())
        self.assert_idle()

    def test_real_flasher_hardware_error_returns_to_idle(self):
        self.page.bin_file = str(self.bin_file)
        with patch('can.interface.Bus', side_effect=RuntimeError('simulated missing hardware')):
            self.page.start_btn.click()
            self.wait_for(lambda: len(self.results) == 1)
        self.assertEqual(self.results, [False])
        self.assertIn('simulated missing hardware', self.page.log_text.toPlainText())
        self.assert_idle()


if __name__ == '__main__':
    unittest.main(verbosity=2)
