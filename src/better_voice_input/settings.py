from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SERVICE = "better-voice-input"


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BetterVoiceInput"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_model_dir() -> Path:
    local = project_root() / "models"
    if local.exists():
        return local
    return data_dir() / "models"


@dataclass
class Settings:
    model: str = "deepseek-flash"
    model_dir: str = ""
    microphone: int | None = None
    auto_insert: bool = True
    hotkey: str = "Ctrl+Shift+Space"
    hold_to_talk: bool = False
    save_history: bool = False
    glossary: list[str] = field(default_factory=lambda: ["DeepSeek", "API", "Windows", "Ctrl", "Shift"])
    api_timeout: float = 25.0

    @property
    def models(self) -> Path:
        return Path(self.model_dir) if self.model_dir else default_model_dir()

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or data_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls()
            defaults = cls()
            values = {}
            for key, value in raw.items():
                if key not in cls.__dataclass_fields__:
                    continue
                if key == "microphone":
                    if value is None or type(value) is int and value >= 0:
                        values[key] = value
                elif key == "glossary":
                    if isinstance(value, list) and all(isinstance(word, str) for word in value):
                        values[key] = [word[:80] for word in value[:100]]
                elif type(value) is type(getattr(defaults, key)):
                    values[key] = value
            if values.get("hotkey") not in (None, "Ctrl+Shift+Space", "Ctrl+Alt+Space", "Alt+Shift+Space"):
                values.pop("hotkey")
            if not 1 <= values.get("api_timeout", 25) <= 120:
                values.pop("api_timeout", None)
            return cls(**values)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or data_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)


def read_key(key_file: Path | None = None) -> str:
    if key_file is not None:
        return key_file.read_text(encoding="utf-8-sig").strip()
    value = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if value:
        return value
    try:
        import keyring

        value = keyring.get_password(SERVICE, "deepseek")
        if value:
            return value
    except Exception:
        pass
    local = project_root() / "deepseek api key.txt"
    if local.is_file():
        return local.read_text(encoding="utf-8-sig").strip()
    return ""


def save_key(value: str) -> None:
    import keyring

    keyring.set_password(SERVICE, "deepseek", value.strip())
