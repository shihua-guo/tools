from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QActionGroup
from PySide6.QtCore import Qt, QTimer
import os
import sys
import keyboard

from .overlay import OverlayWindow
from .editor import EditorWindow
from .services.storage import StorageService
from .services.hotkey import HotkeyService

class ReminderApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.storage = StorageService()
        self.app_data = self.storage.load()

        # Pomodoro State
        self.pomo_seconds = 25 * 60
        self.pomo_timer = QTimer()
        self.pomo_timer.timeout.connect(self.update_pomo)

        # UI Components
        self.overlay = OverlayWindow(self.app_data)
        self.overlay.set_opacity(self.app_data.settings.opacity)
        self.overlay.position_changed.connect(self.on_position_changed)
        self.overlay.show()

        self.editor = EditorWindow(self.app_data)
        self.editor.tasks_updated.connect(self.on_tasks_changed)

        # Services
        self.hotkey = HotkeyService()
        self.hotkey.hotkey_pressed.connect(self.toggle_overlay)

        # Global Modifier Polling
        self.modifier_timer = QTimer()
        self.modifier_timer.timeout.connect(self.check_modifiers)
        self.modifier_timer.start(100)  # Check every 100ms

        self.setup_tray()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)
        
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "app.ico")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else:
            from PySide6.QtGui import QPixmap, QPainter, QColor
            pixmap = QPixmap(64, 64)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setBrush(QColor("cyan"))
            painter.drawEllipse(10, 10, 44, 44)
            painter.end()
            self.tray_icon.setIcon(QIcon(pixmap))

        menu = QMenu()
        
        # Actions
        manage_action = QAction("Manage Tasks...", self.app)
        manage_action.triggered.connect(self.show_editor)
        menu.addAction(manage_action)

        # Pomodoro Submenu
        pomo_menu = menu.addMenu("Pomodoro")
        start_action = QAction("Start", self.app)
        start_action.triggered.connect(self.start_pomo)
        pomo_menu.addAction(start_action)

        stop_action = QAction("Stop", self.app)
        stop_action.triggered.connect(self.stop_pomo)
        pomo_menu.addAction(stop_action)

        reset_action = QAction("Reset", self.app)
        reset_action.triggered.connect(self.reset_pomo)
        pomo_menu.addAction(reset_action)

        # Opacity Submenu
        opacity_menu = menu.addMenu("Opacity")
        for op in [0.2, 0.5, 0.8, 1.0]:
            action = QAction(f"{int(op*100)}%", self.app)
            action.triggered.connect(lambda checked=False, o=op: self.change_opacity(o))
            opacity_menu.addAction(action)

        # Layout Submenu
        layout_menu = menu.addMenu("Layout")
        self.layout_group = QActionGroup(self.app)
        for value, label in [("vertical", "Vertical"), ("horizontal", "Horizontal")]:
            action = QAction(label, self.app)
            action.setCheckable(True)
            action.setChecked(self.app_data.settings.layout_direction == value)
            action.triggered.connect(lambda checked=False, v=value: self.change_layout_direction(v))
            self.layout_group.addAction(action)
            layout_menu.addAction(action)

        # Text Color Submenu
        color_menu = menu.addMenu("Text Color")
        self.color_group = QActionGroup(self.app)
        for value, label in [("white", "White"), ("black", "Black")]:
            action = QAction(label, self.app)
            action.setCheckable(True)
            action.setChecked(self.app_data.settings.text_color == value)
            action.triggered.connect(lambda checked=False, v=value: self.change_text_color(v))
            self.color_group.addAction(action)
            color_menu.addAction(action)

        menu.addSeparator()
        
        exit_action = QAction("Exit", self.app)
        exit_action.triggered.connect(self.quit_app)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def start_pomo(self):
        if not self.pomo_timer.isActive():
            self.pomo_timer.start(1000)

    def stop_pomo(self):
        self.pomo_timer.stop()

    def reset_pomo(self):
        self.pomo_timer.stop()
        self.pomo_seconds = 25 * 60
        self.update_overlay_pomo()

    def update_pomo(self):
        if self.pomo_seconds > 0:
            self.pomo_seconds -= 1
            self.update_overlay_pomo()
        else:
            self.pomo_timer.stop()
            self.overlay.pulse_pomo()
            # Simple beep for notification
            import winsound
            winsound.Beep(1000, 500)

    def update_overlay_pomo(self):
        mins, secs = divmod(self.pomo_seconds, 60)
        pomo_text = f"Pomo: {mins:02d}:{secs:02d}"
        self.overlay.refresh_tasks(pomo_text)

    def show_editor(self):
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    def on_tasks_changed(self):
        self.update_overlay_pomo() # This calls overlay.refresh_tasks
        self.storage.save(self.app_data)

    def on_position_changed(self, x, y):
        self.storage.save(self.app_data)

    def check_modifiers(self):
        try:
            ctrl_pressed = keyboard.is_pressed('ctrl')
            alt_pressed = keyboard.is_pressed('alt')
            self.overlay.set_drag_mode(ctrl_pressed and alt_pressed)
        except Exception:
            pass

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()

    def change_opacity(self, opacity):
        self.app_data.settings.opacity = opacity
        self.overlay.set_opacity(opacity)
        self.storage.save(self.app_data)

    def change_layout_direction(self, direction):
        self.overlay.set_layout_direction(direction)
        self.storage.save(self.app_data)

    def change_text_color(self, color):
        self.overlay.set_text_color(color)
        self.storage.save(self.app_data)

    def quit_app(self):
        self.hotkey.cleanup()
        self.storage.save(self.app_data)
        self.app.quit()

    def run(self):
        sys.exit(self.app.exec())

if __name__ == "__main__":
    reminder = ReminderApp()
    reminder.run()
