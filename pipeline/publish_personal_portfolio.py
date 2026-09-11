#!/usr/bin/env python3
"""Publish the manually maintained personal portfolio for site consumption.

The canonical editable source is data/config/portfolio.json. This script keeps
an identical public copy at data/public/portfolio.json so front-ends can consume
it without depending on configuration paths.
"""
from __future__ import annotations

import json
from pathlib import Path

SOURCE = Path("data/config/portfolio.json")
TARGET = Path("data/public/portfolio.json")


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing portfolio source: {SOURCE}")

    payload = json.loads(SOURCE.read_text())
    if not isinstance(payload, dict) or not isinstance(payload.get("positions"), list):
        raise SystemExit("portfolio.json must be an object containing a positions array")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Published {len(payload['positions'])} portfolio positions to {TARGET}")


if __name__ == "__main__":
    main()
