import json
import time

from better_voice_input.history import HistoryStore
from better_voice_input.settings import Settings


def test_history_encrypts_roundtrips_and_clears(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.append("私密测试原文", "私密测试结果")
    raw = store.path.read_text(encoding="utf8")
    assert "私密测试" not in raw
    rows = store.read()
    assert rows[0]["original"] == "私密测试原文"
    assert rows[0]["text"] == "私密测试结果"
    store.clear()
    assert not store.path.exists()


def test_expired_history_is_removed(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.append("一段话", "结果")
    rows = json.loads(store.path.read_text())
    rows[0]["created"] = time.time() - 8 * 86400
    store.path.write_text(json.dumps(rows))
    assert store.read() == []
    assert json.loads(store.path.read_text()) == []


def test_corrupt_history_is_ignored(tmp_path):
    store = HistoryStore(tmp_path / "history.json")
    store.path.write_text("not json")
    assert store.read() == []


def test_wrong_setting_types_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"auto_insert": "false", "model_dir": 12, "hotkey": "invalid", "glossary": [3]})
    )
    assert Settings.load(path) == Settings()


def test_nonobject_settings_do_not_crash(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]")
    assert Settings.load(path) == Settings()
