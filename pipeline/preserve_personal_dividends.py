#!/usr/bin/env python3
"""Re-inject independently synced personal dividend data into snapshot.json."""

from __future__ import annotations

import json
from pathlib import Path

PERSONAL = Path("data/public/xtb-dividends.json")
SNAPSHOT = Path("data/public/snapshot.json")


def main() -> int:
    if not PERSONAL.exists() or not SNAPSHOT.exists():
        return 0
    personal = json.loads(PERSONAL.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if snapshot.get("personalDividends") == personal:
        return 0
    snapshot["personalDividends"] = personal
    SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
