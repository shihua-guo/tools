from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QListWidget, QListWidgetItem, QMessageBox)
from PySide6.QtCore import Qt, Signal
from .models import AppData, TaskItem

class EditorWindow(QWidget):
    tasks_updated = Signal()

    def __init__(self, app_data: AppData):
        super().__init__()
        self.app_data = app_data
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Manage Tasks - Windows Reminder")
        self.resize(400, 500)
        
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Input area
        input_layout = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText("Enter a new task...")
        self.task_input.returnPressed.connect(self.add_task)
        
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_task)
        
        input_layout.addWidget(self.task_input)
        input_layout.addWidget(add_btn)
        layout.addLayout(input_layout)

        # List area
        self.task_list = QListWidget()
        layout.addWidget(self.task_list)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        complete_btn = QPushButton("Done / Undo")
        complete_btn.clicked.connect(self.toggle_task_completion)
        
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self.delete_task)
        
        btn_layout.addWidget(complete_btn)
        btn_layout.addWidget(delete_btn)
        layout.addLayout(btn_layout)

        self.refresh_list()

    def refresh_list(self):
        self.task_list.clear()
        for task in self.app_data.tasks:
            item = QListWidgetItem(task.content)
            if task.is_completed:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setForeground(Qt.gray)
                item.setText(f"[Done] {task.content}")
            self.task_list.addItem(item)

    def add_task(self):
        content = self.task_input.text().strip()
        if not content:
            return
        
        new_id = max([t.id for t in self.app_data.tasks], default=0) + 1
        new_task = TaskItem(id=new_id, content=content)
        self.app_data.tasks.append(new_task)
        
        self.task_input.clear()
        self.refresh_list()
        self.tasks_updated.emit()

    def toggle_task_completion(self):
        current_row = self.task_list.currentRow()
        if current_row < 0:
            return
            
        task = self.app_data.tasks[current_row]
        task.is_completed = not task.is_completed
        self.refresh_list()
        self.tasks_updated.emit()

    def delete_task(self):
        current_row = self.task_list.currentRow()
        if current_row < 0:
            return
            
        self.app_data.tasks.pop(current_row)
        self.refresh_list()
        self.tasks_updated.emit()
