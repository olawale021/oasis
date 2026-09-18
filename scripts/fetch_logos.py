#!/usr/bin/env python3
"""Club crests for the site: web/public/logos/{team_id}.png, 96px, committed
(nothing hotlinked at runtime). Fetches every club in the exported payload
(web/src/data/live.json) that has no file yet, from the API-Football logo
URL stored on the teams row.

    python3 scripts/fetch_logos.py            # missing clubs in live.json
    python3 scripts/fetch_logos.py 42 85 ...  # specific team ids
"""
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGOS = ROOT / "web" / "public" / "logos"
SIZE = 96


def wanted_ids() -> list:
    if len(sys.argv) > 1:
        return [int(a) for a in sys.argv[1:]]
    live = json.loads((ROOT / "web" / "src" / "data" / "live.json").read_text())
    ids = set()
    for m in live["matches"]:
        ids.update((m["homeId"], m["awayId"]))
    for rows in live.get("standings", {}).values():
        ids.update(r["teamId"] for r in rows)
    return sorted(i for i in ids if not (LOGOS / f"{i}.png").exists())


def downscale(raw: bytes, out: Path) -> None:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img.thumbnail((SIZE, SIZE))
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
        canvas.save(out, "PNG", optimize=True)
    except ImportError:  # macOS fallback
        out.write_bytes(raw)
        subprocess.run(["sips", "-Z", str(SIZE), str(out)], check=True, capture_output=True)


def main() -> None:
    conn = sqlite3.connect(ROOT / "data" / "oasis.sqlite")
    LOGOS.mkdir(parents=True, exist_ok=True)
    ids = wanted_ids()
    done, failed = 0, []
    for team_id in ids:
        row = conn.execute("SELECT name, logo_url FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        if not row or not row[1]:
            failed.append((team_id, "no logo_url"))
            continue
        try:
            # curl rather than urllib: the venv's python has no CA bundle on the laptop.
            raw = subprocess.run(["curl", "-fsSL", "--max-time", "20", "-A", "Mozilla/5.0", row[1]], check=True, capture_output=True).stdout
            downscale(raw, LOGOS / f"{team_id}.png")
            done += 1
            print(f"  {team_id:>6} {row[0]}")
        except Exception as exc:  # noqa: BLE001
            failed.append((team_id, str(exc)))
    print(f"{done} crests written, {len(failed)} failed")
    for team_id, why in failed:
        print(f"  FAILED {team_id}: {why}", file=sys.stderr)


if __name__ == "__main__":
    main()
