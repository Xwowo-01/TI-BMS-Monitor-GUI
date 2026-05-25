from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QFileDialog,
    QProgressBar,
    QCheckBox,
    QFrame
)

import os

from uds.uds_flasher import UDSFlasher


# =========================================================
# 中文
# =========================================================

class UITextCN:

    PAGE_TITLE = "Bootloader 刷写"

    NO_BIN_FILE = "未选择 BIN 文件"

    SELECT_BIN_FILE = "选择 BIN 文件"

    BIN_FILE_FILTER = "BIN Files (*.bin)"

    PLEASE_SELECT_BIN = "请先选择 BIN 文件"

    FILE_SIZE = "BIN 文件大小"

    FILE_SIZE_READ_FAILED = "读取失败"

    SAVE_CAN_LOG = "保存 CAN Log TXT"

    CAN_LOG_TITLE = "CAN 报文日志"

    CURRENT_STAGE = "当前阶段"

    STAGE_IDLE = "待机"

    START_FLASH = "开始刷写"

    FLASH_FINISHED = "===== 刷写完成 ====="

    FLASH_FAILED = "===== 刷写失败 ====="


# =========================================================
# English
# =========================================================

class UITextEN:

    PAGE_TITLE = "Bootloader Flash"

    NO_BIN_FILE = "No BIN File Selected"

    SELECT_BIN_FILE = "Select BIN File"

    BIN_FILE_FILTER = "BIN Files (*.bin)"

    PLEASE_SELECT_BIN = "Please Select BIN File First"

    FILE_SIZE = "BIN File Size"

    FILE_SIZE_READ_FAILED = "Read Failed"

    SAVE_CAN_LOG = "Save CAN Log TXT"

    CAN_LOG_TITLE = "CAN Message Log"

    CURRENT_STAGE = "Current Stage"

    STAGE_IDLE = "Idle"

    START_FLASH = "Start Flash"

    FLASH_FINISHED = "===== Flash Finished ====="

    FLASH_FAILED = "===== Flash Failed ====="


class BootloaderPage(QWidget):

    # =====================================================
    # 信号
    # =====================================================

    starting_flash = Signal()

    finished_flash = Signal(bool)

    current_ui = UITextCN

    # =====================================================
    # INIT
    # =====================================================

    def __init__(self):
        super().__init__()

        self.bin_file = ""

        self.setup_ui()

    # =====================================================
    # UI
    # =====================================================

    def setup_ui(self):

        main = QHBoxLayout(self)

        # =================================================
        # LEFT
        # =================================================

        left = QFrame()

        left.setFixedWidth(350)

        left_layout = QVBoxLayout(left)

        # Title

        self.title_label = QLabel(
            self.current_ui.PAGE_TITLE
        )

        self.title_label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
        """)

        left_layout.addWidget(
            self.title_label
        )

        # =================================================
        # 文件选择
        # =================================================

        self.file_label = QLabel(
            self.current_ui.NO_BIN_FILE
        )

        self.file_btn = QPushButton(
            self.current_ui.SELECT_BIN_FILE
        )

        self.file_btn.clicked.connect(
            self.choose_file
        )

        left_layout.addWidget(
            self.file_label
        )

        left_layout.addWidget(
            self.file_btn
        )

        # =================================================
        # 文件大小
        # =================================================

        self.file_size_label = QLabel(
            f"{self.current_ui.FILE_SIZE}：0 KB"
        )

        self.file_size_label.setStyleSheet("""
            font-size: 13px;
            color: #555555;
        """)

        left_layout.addWidget(
            self.file_size_label
        )

        # =================================================
        # 日志保存
        # =================================================

        self.log_checkbox = QCheckBox(
            self.current_ui.SAVE_CAN_LOG
        )

        left_layout.addWidget(
            self.log_checkbox
        )

        # =================================================
        # 阶段
        # =================================================

        self.stage_label = QLabel(
            f"{self.current_ui.CURRENT_STAGE}："
            f"{self.current_ui.STAGE_IDLE}"
        )

        self.stage_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #2E86DE;
        """)

        left_layout.addWidget(
            self.stage_label
        )

        # =================================================
        # Progress
        # =================================================

        self.progress = QProgressBar()

        self.progress.setValue(0)

        left_layout.addWidget(
            self.progress
        )

        # =================================================
        # Start
        # =================================================

        self.start_btn = QPushButton(
            self.current_ui.START_FLASH
        )

        self.start_btn.clicked.connect(
            self.start_flash
        )

        left_layout.addWidget(
            self.start_btn
        )

        left_layout.addStretch()

        main.addWidget(left)

        # =================================================
        # RIGHT LOG
        # =================================================

        right = QVBoxLayout()

        self.log_title_label = QLabel(
            self.current_ui.CAN_LOG_TITLE
        )

        self.log_title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
        """)

        self.log_text = QTextEdit()

        self.log_text.setReadOnly(True)

        right.addWidget(
            self.log_title_label
        )

        right.addWidget(
            self.log_text
        )

        main.addLayout(right)

    # =====================================================
    # 语言切换
    # =====================================================

    def switch_language(self, language="cn"):

        self.current_ui = (
            UITextEN
            if language.lower() == "en"
            else UITextCN
        )

        ui = self.current_ui

        self.title_label.setText(
            ui.PAGE_TITLE
        )

        self.file_btn.setText(
            ui.SELECT_BIN_FILE
        )

        self.log_checkbox.setText(
            ui.SAVE_CAN_LOG
        )

        self.start_btn.setText(
            ui.START_FLASH
        )

        self.log_title_label.setText(
            ui.CAN_LOG_TITLE
        )

        self.stage_label.setText(
            f"{ui.CURRENT_STAGE}："
            f"{ui.STAGE_IDLE}"
        )

        if not self.bin_file:

            self.file_label.setText(
                ui.NO_BIN_FILE
            )

            self.file_size_label.setText(
                f"{ui.FILE_SIZE}：0 KB"
            )

        else:

            self.update_file_size_label()

    # =====================================================
    # 文件选择
    # =====================================================

    def choose_file(self):

        filename, _ = QFileDialog.getOpenFileName(
            self,
            self.current_ui.SELECT_BIN_FILE,
            "",
            self.current_ui.BIN_FILE_FILTER
        )

        if filename:

            self.bin_file = filename

            self.file_label.setText(
                filename
            )

            self.update_file_size_label()

    # =====================================================
    # 文件大小
    # =====================================================

    def update_file_size_label(self):

        try:

            file_size = os.path.getsize(
                self.bin_file
            )

            if file_size >= 1024 * 1024:

                size_text = (
                    f"{file_size / (1024 * 1024):.2f} MB"
                )

            else:

                size_text = (
                    f"{file_size / 1024:.2f} KB"
                )

            self.file_size_label.setText(
                f"{self.current_ui.FILE_SIZE}："
                f"{size_text}"
            )

        except Exception:

            self.file_size_label.setText(
                f"{self.current_ui.FILE_SIZE}："
                f"{self.current_ui.FILE_SIZE_READ_FAILED}"
            )

    # =====================================================
    # 开始刷写
    # =====================================================

    def start_flash(self):

        if not self.bin_file:

            self.log_text.append(
                self.current_ui.PLEASE_SELECT_BIN
            )

            return

        # =============================================
        # 通知 Main 停止 CANReceiver
        # =============================================

        self.starting_flash.emit()

        self.progress.setValue(0)

        self.log_text.clear()

        # =============================================
        # 创建线程
        # =============================================

        self.thread = QThread()

        self.flasher = UDSFlasher(
            self.bin_file,
            self.log_checkbox.isChecked()
        )

        self.flasher.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.flasher.flash
        )

        self.flasher.log_signal.connect(
            self.append_log
        )

        self.flasher.progress_signal.connect(
            self.progress.setValue
        )

        self.flasher.stage_signal.connect(
            self.update_stage
        )

        self.flasher.finished_signal.connect(
            self._flash_finished
        )

        self.thread.start()

    # =====================================================
    # 刷写完成
    # =====================================================

    def _flash_finished(self, success):

        # =============================================
        # 先彻底关闭线程
        # =============================================

        if hasattr(self, "thread"):

            if self.thread.isRunning():

                self.thread.quit()

                self.thread.wait()

        # =============================================
        # UI
        # =============================================

        if success:

            self.log_text.append(
                self.current_ui.FLASH_FINISHED
            )

        else:

            self.log_text.append(
                self.current_ui.FLASH_FAILED
            )

        # =============================================
        # 通知 Main 恢复 CAN
        # =============================================

        self.finished_flash.emit(success)

    # =====================================================
    # LOG
    # =====================================================

    def append_log(self, text):

        self.log_text.append(text)

        scrollbar = (
            self.log_text.verticalScrollBar()
        )

        scrollbar.setValue(
            scrollbar.maximum()
        )

    # =====================================================
    # 阶段更新
    # =====================================================

    def update_stage(self, text):

        self.stage_label.setText(
            f"{self.current_ui.CURRENT_STAGE}：{text}"
        )