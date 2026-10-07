from better_voice_input import settings


def test_default_shortcut_is_two_keys_and_hold_to_talk_is_enabled():
    value = settings.Settings()
    assert value.hotkey == "Alt+X"
    assert value.hold_to_talk


def test_two_key_shortcut_survives_reload(tmp_path):
    value = settings.Settings(hotkey="Alt+C")
    path = tmp_path / "settings.json"
    value.save(path)
    assert settings.Settings.load(path) == value


def test_legacy_preview_preferences_do_not_disable_direct_input(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"auto_insert":false,"review_warnings":true}', encoding="utf-8")
    assert settings.Settings.load(path) == settings.Settings()


def test_packaged_build_finds_project_models_without_saved_config(tmp_path, monkeypatch):
    binary = tmp_path / "dist" / "BetterVoiceInput" / "BetterVoiceInput.exe"
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings.sys, "executable", str(binary))
    assert settings.Settings().models == models


def test_models_beside_executable_take_precedence(tmp_path, monkeypatch):
    binary = tmp_path / "dist" / "BetterVoiceInput" / "BetterVoiceInput.exe"
    local = binary.parent / "models"
    local.mkdir(parents=True)
    (tmp_path / "models").mkdir()
    monkeypatch.setattr(settings.sys, "frozen", True, raising=False)
    monkeypatch.setattr(settings.sys, "executable", str(binary))
    assert settings.Settings().models == local
