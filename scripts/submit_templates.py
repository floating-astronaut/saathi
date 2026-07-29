"""Submit message templates to the WABA. Idempotent-ish: reports conflicts."""
from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from saathi.wa.templates import TEMPLATES, validate  # noqa: E402

GRAPH = "https://graph.facebook.com/v21.0"


def env(key: str) -> str:
    m = re.search(rf"^{key}=(.*)$", pathlib.Path(".env").read_text(), re.M)
    return (m.group(1).strip() if m else "")


def main() -> int:
    problems = validate()
    if problems:
        print("local validation failed:", *problems, sep="\n  ")
        return 1
    token, waba = env("WA_ACCESS_TOKEN"), env("WA_BUSINESS_ACCOUNT_ID")
    if not token or not waba:
        print("missing WA_ACCESS_TOKEN or WA_BUSINESS_ACCOUNT_ID")
        return 1
    rc = 0
    for t in TEMPLATES:
        body = urllib.parse.urlencode({
            "name": t["name"], "language": t["language"], "category": t["category"],
            "components": json.dumps(t["components"]), "access_token": token,
        }).encode()
        try:
            r = json.load(urllib.request.urlopen(
                urllib.request.Request(f"{GRAPH}/{waba}/message_templates", data=body)))
            print(f"  {t['name']:16s} submitted  id={r.get('id')} status={r.get('status')}")
        except urllib.error.HTTPError as e:
            err = json.loads(e.read().decode()).get("error", {})
            print(f"  {t['name']:16s} FAILED  {err.get('message')} "
                  f"| {err.get('error_user_msg') or ''}"[:170])
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
