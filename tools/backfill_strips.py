#!/usr/bin/env python3
"""Phase 2 — put the existing candidates in front of the judge.

Every unapproved clip that was gathered before the judge existed gets a 3-frame
contact strip built from its Release preview, uploaded to the lesson's media
shard, and is marked judged:false. The next push then fires the judge routine,
which captions, scores and ranks them and hides the junk. Approved clips are
never touched.

    python3 tools/backfill_strips.py <slug> [--max N]
"""
import json, os, sys, time, pathlib, tempfile, subprocess
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release_media as rm
from recall import make_strip

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = "CAA-Broll-Studio-Bot/1.0"


def main(slug, max_n=None):
    card_p = ROOT / "projects" / slug / "scenes.json"
    card = json.load(open(card_p))
    sel_p = ROOT / "selections" / f"{slug}.json"
    approved = set()
    if sel_p.exists():
        approved = {x for v in (json.load(open(sel_p)).get("approved") or {}).values() for x in v}
    todo = [(s, c) for s in card["scenes"] for c in s.get("clips", [])
            if c.get("type", "video") == "video" and c["id"] not in approved
            and "judged" not in c and not c.get("strip") and str(c.get("preview", "")).startswith("http")]
    if max_n:
        todo = todo[:max_n]
    print(f"{slug}: {len(todo)} unjudged, unapproved clips to strip")
    done = fail = 0
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        for i, (s, c) in enumerate(todo, 1):
            pv = td / f"{c['id']}.mp4"; st = td / f"{c['id']}.strip.jpg"
            try:
                with requests.get(c["preview"], stream=True, timeout=120, headers={"User-Agent": UA}) as r:
                    r.raise_for_status()
                    with open(pv, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
            except Exception as e:
                print(f"  {c['id']}: preview download failed: {str(e)[:60]}"); fail += 1; continue
            if not make_strip(pv, st):
                print(f"  {c['id']}: strip failed"); fail += 1; pv.unlink(missing_ok=True); continue
            url = rm.upload_for_slug(slug, rm.asset_name(s["id"], "strip", st), st)
            pv.unlink(missing_ok=True); st.unlink(missing_ok=True)
            if not url:
                print(f"  {c['id']}: strip upload failed"); fail += 1; continue
            c["strip"] = url
            c["judged"] = False
            done += 1
            if i % 25 == 0:
                json.dump(card, open(card_p, "w"), indent=1, ensure_ascii=False)
                print(f"  … {i}/{len(todo)} ({done} ok, {fail} failed)")
    json.dump(card, open(card_p, "w"), indent=1, ensure_ascii=False)
    print(f"{slug}: {done} clips ready for the judge, {fail} failed")


if __name__ == "__main__":
    a = sys.argv[1:]
    mx = int(a[a.index("--max") + 1]) if "--max" in a else None
    main(a[0], mx)
