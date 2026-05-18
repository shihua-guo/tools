from PySide6.QtWidgets import QWidget, QBoxLayout, QLabel, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent
from .models import AppData

class OverlayWindow(QWidget):
    position_changed = Signal(int, int)

    def __init__(self, app_data: AppData):
        super().__init__()
        self.app_data = app_data
        self.drag_active = False
        self.drag_start_pos = QPoint()
        self._current_pomo_text = None
        self.init_ui()

    def init_ui(self):
        # Set window flags for frameless, always-on-top, and tool window (no taskbar icon)
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool |
            Qt.WindowTransparentForInput  # This makes it click-through
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.labels = []
        self.pomo_label = None
        self._build_layout()
        self.refresh_tasks()

        # Position at top-right
        self.update_position()

    def refresh_tasks(self, pomo_text=None):
        self._current_pomo_text = pomo_text

        # Clear existing labels
        for label in self.labels:
            self.task_layout.removeWidget(label)
            label.deleteLater()
        self.labels.clear()
        
        if self.pomo_label:
            self.task_layout.removeWidget(self.pomo_label)
            self.pomo_label.deleteLater()
            self.pomo_label = None

        self._ensure_layout_direction()

        font = QFont("Microsoft YaHei", 14, QFont.Bold)
        text_color = self._task_text_color()
        
        # Add tasks
        for task in self.app_data.tasks:
            if not task.is_completed:
                label = self._create_label(task.content, font, text_color)
                self.task_layout.addWidget(label)
                self.labels.append(label)

        # Add Pomodoro timer at the bottom
        if pomo_text:
            self.pomo_label = self._create_label(pomo_text, font, "#FFCC00") # Yellowish/Orange
            self.task_layout.addWidget(self.pomo_label)

    def _build_layout(self):
        current_layout = self.layout()
        if current_layout:
            QWidget().setLayout(current_layout)

        direction = (
            QBoxLayout.LeftToRight
            if self.app_data.settings.layout_direction == "horizontal"
            else QBoxLayout.TopToBottom
        )
        self.task_layout = QBoxLayout(direction)
        self.task_layout.setContentsMargins(8, 8, 8, 8)
        self.task_layout.setSpacing(12 if direction == QBoxLayout.LeftToRight else 4)
        self.task_layout.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.setLayout(self.task_layout)
        self._active_layout_direction = self.app_data.settings.layout_direction

    def _ensure_layout_direction(self):
        if getattr(self, "_active_layout_direction", None) != self.app_data.settings.layout_direction:
            self._build_layout()

    def _task_text_color(self):
        if self.app_data.settings.text_color == "black":
            return "black"
        return "white"

    def _create_label(self, text, font, color):
        label = QLabel(text)
        label.setFont(font)
        label.setStyleSheet(f"color: {color};")
        
        # Add drop shadow for readability
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(5)
        shadow.setColor(QColor(255, 255, 255, 180) if color == "black" else QColor(0, 0, 0, 200))
        shadow.setOffset(2, 2)
        label.setGraphicsEffect(shadow)
        return label

    def pulse_pomo(self):
        if self.pomo_label:
            self.pomo_label.setStyleSheet("color: #FF4500;") # Deep Orange

    def update_position(self):
        if self.app_data.settings.layout_direction == "horizontal":
            self.resize(900, 120)
        else:
            self.resize(400, 600)
        if self.app_data.settings.pos_x != -1 and self.app_data.settings.pos_y != -1:
            self.move(self.app_data.settings.pos_x, self.app_data.settings.pos_y)
        else:
            screen = self.screen().availableGeometry()
            # Offset from top-right corner
            x = screen.width() - self.width() - 20
            y = 20
            self.move(x, y)

    def set_opacity(self, opacity: float):
        self.setWindowOpacity(opacity)

    def set_layout_direction(self, direction: str):
        self.app_data.settings.layout_direction = direction
        self.refresh_tasks(self._current_pomo_text)
        self.update_position()

    def set_text_color(self, color: str):
        self.app_data.settings.text_color = color
        self.refresh_tasks(self._current_pomo_text)

    def set_drag_mode(self, active: bool):
        if self.drag_active == active:
            return
        
        self.drag_active = active
        if active:
            # Remove transparent for input to capture mouse, add visual indicator
            self.setWindowFlags(
                Qt.FramelessWindowHint | 
                Qt.WindowStaysOnTopHint | 
                Qt.Tool
            )
            self.setStyleSheet("background-color: rgba(0, 0, 0, 50); border: 2px dashed #FFF;")
            self.show()  # Required to apply flag changes
        else:
            # Restore original flags and look
            self.setWindowFlags(
                Qt.FramelessWindowHint | 
                Qt.WindowStaysOnTopHint | 
                Qt.Tool |
                Qt.WindowTransparentForInput
            )
            self.setStyleSheet("")
            self.show()

    def mousePressEvent(self, event: QMouseEvent):
        if self.drag_active and event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_active and not self.drag_start_pos.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drag_active and event.button() == Qt.LeftButton:
            self.drag_start_pos = QPoint()
            # Save new position
            new_pos = self.pos()
            self.app_data.settings.pos_x = new_pos.x()
            self.app_data.settings.pos_y = new_pos.y()
            self.position_changed.emit(new_pos.x(), new_pos.y())
            event.accept()
