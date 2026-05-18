import json
import os
from ..models import AppData

class StorageService:
    def __init__(self, filename="items.json"):
        # Store in AppData folder for persistence
        app_data_dir = os.path.join(os.environ.get("APPDATA", ""), "Windows-Reminder")
        if not os.path.exists(app_data_dir):
            os.makedirs(app_data_dir)
            
        self.filepath = os.path.join(app_data_dir, filename)

    def load(self) -> AppData:
        if not os.path.exists(self.filepath):
            return AppData()
        
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return AppData.from_dict(data)
        except Exception as e:
            print(f"Error loading data: {e}")
            return AppData()

    def save(self, app_data: AppData):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(app_data.to_dict(), f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving data: {e}")
