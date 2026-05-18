import keyboard
from PySide6.QtCore import QObject, Signal

class HotkeyService(QObject):
    hotkey_pressed = Signal()

    def __init__(self, hotkey="ctrl+shift+r"):
        super().__init__()
        self.hotkey = hotkey
        try:
            keyboard.add_hotkey(self.hotkey, self.on_hotkey)
        except Exception as e:
            print(f"Failed to register hotkey: {e}")

    def on_hotkey(self):
        self.hotkey_pressed.emit()

    def cleanup(self):
        keyboard.unhook_all()
