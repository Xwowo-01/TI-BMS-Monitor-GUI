# pages/setting.py

from PySide6.QtCore import (
    Qt,
    Signal,
    QSettings
)

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QHBoxLayout,
    QLineEdit,
    QFormLayout
)

from language_manager import language_manager


# =========================================================
# 中文
# =========================================================

class UITextZH:

    PAGE_TEXT = "配置情况（待补充）"

    LANGUAGE_TITLE = "语言"

    SWITCH_ZH = "中文"

    SWITCH_EN = "English"

    APP_NAME = "应用名"

    CHANNEL = "通道"

    ARB_BITRATE = "仲裁域波特率"

    DATA_BITRATE = "数据域波特率"

    RECONNECT_CAN = "重新连接 CAN"


# =========================================================
# English
# =========================================================

class UITextEN:

    PAGE_TEXT = "Configuration Page (To Be Added)"

    LANGUAGE_TITLE = "Language"

    SWITCH_ZH = "中文"

    SWITCH_EN = "English"

    APP_NAME = "App Name"

    CHANNEL = "Channel"

    ARB_BITRATE = "Arbitration Bitrate"

    DATA_BITRATE = "Data Bitrate"

    RECONNECT_CAN = "Reconnect CAN"


class SettingUI(QWidget):

    reconnect_requested = Signal(
        str,
        int,
        int,
        int
    )

    def __init__(self):
        super().__init__()

        self.current_text = UITextZH

        # =================================================
        # 配置存储
        # =================================================

        self.settings = QSettings(
            "BatteryMonitor",
            "CANConfig"
        )

        self.setup_ui()

        # =================================================
        # 先连接语言信号
        # =================================================

        language_manager.language_changed.connect(
            self.switch_language
        )

        # =================================================
        # 再加载配置
        # =================================================

        self.load_saved_config()

        # =================================================
        # 初始化当前语言
        # （不要依赖 signal 初始化）
        # =================================================

    # =====================================================
    # UI
    # =====================================================

    def setup_ui(self):

        layout = QVBoxLayout(self)

        # =================================================
        # 左上角语言切换
        # =================================================

        top_layout = QHBoxLayout()

        self.lang_label = QLabel(
            f"{self.current_text.LANGUAGE_TITLE}："
        )

        self.lang_label.setStyleSheet("""
            font-size: 13px;
            color: #555555;
        """)

        self.zh_btn = QPushButton(
            self.current_text.SWITCH_ZH
        )

        self.en_btn = QPushButton(
            self.current_text.SWITCH_EN
        )

        btn_style = """
            QPushButton {
                border: 1px solid #C8C8C8;
                border-radius: 4px;
                padding: 4px 10px;
                background: white;
                color: #333333;
            }

            QPushButton:hover {
                background: #F5F5F5;
            }

            QPushButton:pressed {
                background: #EAEAEA;
            }
        """

        self.zh_btn.setStyleSheet(btn_style)

        self.en_btn.setStyleSheet(btn_style)

        self.zh_btn.setFlat(True)

        self.en_btn.setFlat(True)

        self.zh_btn.setCursor(
            Qt.PointingHandCursor
        )

        self.en_btn.setCursor(
            Qt.PointingHandCursor
        )

        self.zh_btn.clicked.connect(
            lambda:
            language_manager.set_language("zh")
        )

        self.en_btn.clicked.connect(
            lambda:
            language_manager.set_language("en")
        )

        top_layout.addWidget(
            self.lang_label
        )

        top_layout.addWidget(
            self.zh_btn
        )

        top_layout.addWidget(
            self.en_btn
        )

        top_layout.addStretch()

        layout.addLayout(top_layout)

        # =================================================
        # CAN 配置
        # =================================================

        form_layout = QFormLayout()

        self.app_name_edit = QLineEdit()

        self.channel_edit = QLineEdit()

        self.arb_bitrate_edit = QLineEdit()

        self.data_bitrate_edit = QLineEdit()

        self.app_name_label = QLabel(
            self.current_text.APP_NAME
        )

        self.channel_label = QLabel(
            self.current_text.CHANNEL
        )

        self.arb_label = QLabel(
            self.current_text.ARB_BITRATE
        )

        self.data_label = QLabel(
            self.current_text.DATA_BITRATE
        )

        form_layout.addRow(
            self.app_name_label,
            self.app_name_edit
        )

        form_layout.addRow(
            self.channel_label,
            self.channel_edit
        )

        form_layout.addRow(
            self.arb_label,
            self.arb_bitrate_edit
        )

        form_layout.addRow(
            self.data_label,
            self.data_bitrate_edit
        )

        layout.addLayout(form_layout)

        # =================================================
        # 重连按钮
        # =================================================

        self.reconnect_btn = QPushButton(
            self.current_text.RECONNECT_CAN
        )

        self.reconnect_btn.clicked.connect(
            self.on_reconnect_clicked
        )

        layout.addWidget(
            self.reconnect_btn
        )

        # =================================================
        # 页面内容
        # =================================================

        self.label = QLabel(
            self.current_text.PAGE_TEXT
        )

        self.label.setAlignment(
            Qt.AlignCenter
        )

        self.label.setStyleSheet("""
            color: gray;
            font-size: 16px;
        """)

        layout.addStretch()

        layout.addWidget(
            self.label
        )

        layout.addStretch()

    # =====================================================
    # 加载历史配置
    # =====================================================

    def load_saved_config(self):

        app_name = self.settings.value(
            "app_name",
            "VectorTest"
        )

        channel = self.settings.value(
            "channel",
            0
        )

        arb_bitrate = self.settings.value(
            "arb_bitrate",
            1000000
        )

        data_bitrate = self.settings.value(
            "data_bitrate",
            1000000
        )

        self.app_name_edit.setText(
            str(app_name)
        )

        self.channel_edit.setText(
            str(channel)
        )

        self.arb_bitrate_edit.setText(
            str(arb_bitrate)
        )

        self.data_bitrate_edit.setText(
            str(data_bitrate)
        )

        saved_language = self.settings.value(
            "language",
            "zh"
        )

        language_manager.set_language(
            saved_language
        )

    # =====================================================
    # 点击重连
    # =====================================================

    def on_reconnect_clicked(self):

        try:

            app_name = (
                self.app_name_edit.text().strip()
            )

            channel = int(
                self.channel_edit.text()
            )

            arb_bitrate = int(
                self.arb_bitrate_edit.text()
            )

            data_bitrate = int(
                self.data_bitrate_edit.text()
            )

            # =============================================
            # 保存配置
            # =============================================

            self.settings.setValue(
                "app_name",
                app_name
            )

            self.settings.setValue(
                "channel",
                channel
            )

            self.settings.setValue(
                "arb_bitrate",
                arb_bitrate
            )

            self.settings.setValue(
                "data_bitrate",
                data_bitrate
            )

            # =============================================
            # 发射重连信号
            # =============================================

            self.reconnect_requested.emit(
                app_name,
                channel,
                arb_bitrate,
                data_bitrate
            )

        except Exception as e:

            print(f"参数错误: {e}")

    # =====================================================
    # 语言切换
    # =====================================================

    def switch_language(self, language):

        if language == "en":

            self.current_text = UITextEN

        else:

            self.current_text = UITextZH

        self.update_ui_text()

        self.settings.setValue(
            "language",
            language
        )

    # =====================================================
    # 更新 UI
    # =====================================================

    def update_ui_text(self):

        self.label.setText(
            self.current_text.PAGE_TEXT
        )

        self.lang_label.setText(
            f"{self.current_text.LANGUAGE_TITLE}："
        )

        self.zh_btn.setText(
            self.current_text.SWITCH_ZH
        )

        self.en_btn.setText(
            self.current_text.SWITCH_EN
        )

        self.app_name_label.setText(
            self.current_text.APP_NAME
        )

        self.channel_label.setText(
            self.current_text.CHANNEL
        )

        self.arb_label.setText(
            self.current_text.ARB_BITRATE
        )

        self.data_label.setText(
            self.current_text.DATA_BITRATE
        )

        self.reconnect_btn.setText(
            self.current_text.RECONNECT_CAN
        )