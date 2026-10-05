from better_voice_input import settings


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
