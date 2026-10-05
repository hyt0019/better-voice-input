@echo off
cd /d "%~dp0"
if exist "dist\BetterVoiceInput\BetterVoiceInput.exe" (
  start "" "dist\BetterVoiceInput\BetterVoiceInput.exe" --background
) else (
  start "" ".venv\Scripts\pythonw.exe" "scripts\run_app.py" --background
)
