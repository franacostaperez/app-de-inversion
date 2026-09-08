#!/usr/bin/env python3
"""Read the XTB Google Sheet and publish personal dividend cash data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

from xtb_dividends import build_payload, normalize_rows, write_payload

SHEET_ID = os.getenv("XTB_DIVIDENDS_SHEET_ID", "1mdd3ZsegDHW1r30o-TKr-QznivG0uBNA3EUCk_ikHa0")
TAB = os.getenv("XTB_DIVIDENDS_TAB", "Dividendos")


def read_values() -> list[list[object]]:
    credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not credentials_json:
        raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON is required")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise SystemExit("Install google-auth and requests") from exc

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    session = AuthorizedSession(credentials)
    encoded_range = quote(f"{TAB}!A:J", safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{encoded_range}"
    response = session.get(
        url,
        params={"valueRenderOption": "FORMATTED_VALUE", "dateTimeRenderOption": "FORMATTED_STRING"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("values", [])


def main() -> int:
    payload = build_payload(normalize_rows(read_values()))
    write_payload(
        payload,
        Path("data/public/xtb-dividends.json"),
        Path("data/public/snapshot.json"),
    )
    print(f"Published {len(payload['receipts'])} XTB receipts through {payload['asOf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
