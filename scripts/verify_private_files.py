"""Fail before commit/push if a known local secret or private asset is tracked."""

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
key_file = root / "deepseek api key.txt"
secret = key_file.read_text(encoding="utf-8-sig").strip().encode() if key_file.exists() else b""
paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
bad = []
for name in filter(None, paths):
    path = root / name
    if (
        name.startswith(("示例语音/", "models/", "private/", ".venv/"))
        or "key" in name.lower()
        and name.endswith(".txt")
    ):
        bad.append(name)
    elif path.is_file() and secret and secret in path.read_bytes():
        bad.append(name)
if bad:
    raise SystemExit("Private content detected in tracked files: " + ", ".join(bad))
print("Tracked files contain no local test key or private assets.")
