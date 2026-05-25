from PySide6.QtCore import QObject, Signal


class LanguageManager(QObject):

    language_changed = Signal(str)

    def __init__(self):
        super().__init__()

        self.current_language = "zh"

    def set_language(self, language):

        if language == self.current_language:
            return

        self.current_language = language

        self.language_changed.emit(language)


language_manager = LanguageManager()