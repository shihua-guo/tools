from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class TaskItem:
    id: int
    content: str
    is_completed: bool = False

@dataclass
class AppSettings:
    opacity: float = 0.5
    position: str = "TopRight"
    pos_x: int = -1
    pos_y: int = -1
    always_on_top: bool = True
    run_at_startup: bool = False
    layout_direction: str = "vertical"
    text_color: str = "white"

@dataclass
class AppData:
    settings: AppSettings = field(default_factory=AppSettings)
    tasks: List[TaskItem] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        settings_data = data.get("settings", {})
        settings = AppSettings(
            opacity=float(settings_data.get("opacity", 0.5)),
            position=str(settings_data.get("position", "TopRight")),
            pos_x=int(settings_data.get("pos_x", -1)),
            pos_y=int(settings_data.get("pos_y", -1)),
            always_on_top=bool(settings_data.get("always_on_top", True)),
            run_at_startup=bool(settings_data.get("run_at_startup", False)),
            layout_direction=str(settings_data.get("layout_direction", "vertical")),
            text_color=str(settings_data.get("text_color", "white"))
        )
        tasks = []
        for t in data.get("tasks", []):
            tasks.append(TaskItem(
                id=int(t.get("id", 0)),
                content=str(t.get("content", "")),
                is_completed=bool(t.get("is_completed", False))
            ))
        return cls(settings=settings, tasks=tasks)
