#!/usr/bin/env python3
"""Fetch full-resolution masters for APPROVED clips only, to the SSD.

The cockpit keeps 480p previews on Releases; masters are never stored in the
cloud. When a clip is approved, this pulls the original from its source by id
(download_url recorded at gather time) into the render library on the SSD, so
render time never depends on a second search. Idempotent — re-runs skip what
already exists. Run on the Mac (needs the SSD), e.g. before a render:

    python3 tools/fetch_masters.py                 # every lesson
    python3 tools/fetch_masters.py edenrise-c2-kaizen
"""
import json, os, pathlib, sys, time
import requests

COCK = pathlib.Path(__file__).resolve().parent.parent
DEST = pathlib.Path(os.environ.get("BROLL_MASTERS", "/Volumes/Ultra Touch/Broll-Masters"))
UA = "CAA-Broll-Studio/1.0"

def main(only=None):
    if not DEST.parent.exists():
        sys.exit(f"SSD not mounted: {DEST.parent}")
    DEST.mkdir(parents=True, exist_ok=True)
    got = skipped = missing = 0
    for sel_p in sorted(COCK.glob("selections/*.json")):
        sel = json.load(open(sel_p)); slug = sel.get("project") or sel_p.stem
        if only and slug != only: continue
        card_p = COCK / "projects" / slug / "scenes.json"
        if not card_p.exists(): continue
        clips = {c["id"]: c for s in json.load(open(card_p))["scenes"] for c in s["clips"]}
        for sid, ids in (sel.get("approved") or {}).items():
            for cid in ids:
                c = clips.get(cid)
                if not c: continue
                url = c.get("download_url")
                if not url:
                    missing += 1; print(f"  ! {slug} {sid} {cid[:40]}: no download_url recorded"); continue
                ext = ".mp4" if c.get("type") == "video" else ".jpg"
                out = DEST / slug / sid / f"{cid}{ext}"
                if out.exists() and out.stat().st_size > 50_000:
                    skipped += 1; continue
                out.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with requests.get(url, stream=True, timeout=180, headers={"User-Agent": UA}) as r:
                        r.raise_for_status()
                        with open(out, "wb") as fh:
                            for chunk in r.iter_content(1 << 20): fh.write(chunk)
                    got += 1; print(f"  + {slug} {sid} {cid[:44]} ({out.stat().st_size//1024} KB)")
                    time.sleep(0.5)
                except Exception as e:
                    missing += 1; print(f"  ! {slug} {sid} {cid[:40]}: {str(e)[:70]}")
    print(f"\nfetched {got}, already had {skipped}, unavailable {missing} → {DEST}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
