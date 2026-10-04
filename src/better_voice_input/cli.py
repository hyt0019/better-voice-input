from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cleanup import CleanupError, DeepSeekCleaner
from .settings import Settings, read_key


def main() -> int:
    parser = argparse.ArgumentParser(description="Better Voice Input diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)
    clean = sub.add_parser("clean", help="整理 UTF-8 文本文件")
    clean.add_argument("input", type=Path)
    clean.add_argument("--key-file", type=Path)
    clean.add_argument("--model", default=None)
    args = parser.parse_args()
    settings = Settings.load()
    try:
        result = DeepSeekCleaner(read_key(args.key_file), args.model or settings.model).clean(
            args.input.read_text(encoding="utf-8-sig"), settings.glossary
        )
        print(
            json.dumps(
                {
                    "text": result.text,
                    "warnings": result.warnings,
                    "elapsed": round(result.elapsed, 2),
                    "usage": result.usage,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (CleanupError, OSError) as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
