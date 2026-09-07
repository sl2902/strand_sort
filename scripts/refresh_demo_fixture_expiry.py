"""
Recomputes expiry_status/is_expired for every demo fixture in
frontend/public/demo/*.json, using the same compute_expiry_status the real
API calls on every read. Demo fixtures are static JSON with expiry_status
frozen at authoring time — that value goes stale as "today" moves forward
(e.g. a "fine" item drifting into its near-expiry window). Run this once
before recording, rather than duplicating the threshold logic client-side
(lib/format.ts's expiryBadgeContent deliberately does NOT recompute this
itself, after an earlier client-side threshold quietly drifted from the
backend's — see its own comment).

Usage:
    uv run scripts/refresh_demo_fixture_expiry.py
"""
import json
from pathlib import Path

from strand_sort.expiry import compute_expiry_status

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "frontend" / "public" / "demo"


def main():
    for fixture_path in sorted(DEMO_DIR.glob("*.json")):
        if fixture_path.name == "manifest.json":
            continue
        item = json.loads(fixture_path.read_text())
        status = compute_expiry_status(item.get("expiration_date"))
        old_status = item.get("expiry_status")
        item["expiry_status"] = status.value if status else None
        item["is_expired"] = status is not None and status.value == "expired"
        fixture_path.write_text(json.dumps(item, indent=2) + "\n")
        changed = " (changed)" if old_status != item["expiry_status"] else ""
        print(f"{fixture_path.name}: {old_status} -> {item['expiry_status']}{changed}")


if __name__ == "__main__":
    main()
