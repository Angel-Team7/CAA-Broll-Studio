#!/usr/bin/env python3
"""Phase 3 — the taste loop. The reviewer's most recent approvals per brand become a
reference sheet the judge looks at before scoring, so every verdict is calibrated to
what the client actually ticks, not to a written rule alone.

    python3 tools/exemplars.py            # rebuild both brands' sheets, upload, write library/exemplars.json

Sheets are uploaded to the shared media shard (never committed); library/exemplars.json
holds the URLs plus the clip ids they were built from, so a rebuild is skipped when the
approvals have not changed.
"""
import io, json, sys, time, pathlib, glob
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release_media as rm

ROOT = pathlib.Path(__file__).resolve().parent.parent
N = 8                     # approvals per sheet
UA = "CAA-Broll-Studio-Bot/1.0"


def recent_approvals(brand):
    rows = []
    for sel in glob.glob(str(ROOT / "selections" / "*.json")):
        slug = pathlib.Path(sel).stem
        if (slug.startswith("belong")) != (brand == "belong") or slug == "belong-module7":
            continue
        d = json.load(open(sel))
        card_p = ROOT / "projects" / slug / "scenes.json"
        if not card_p.exists():
            continue
        clips = {c["id"]: (s, c) for s in json.load(open(card_p))["scenes"] for c in s["clips"]}
        stamp = d.get("updated") or ""
        for sid, ids in (d.get("approved") or {}).items():
            for cid in ids:
                if cid in clips and str(clips[cid][1].get("thumb", "")).startswith("http"):
                    s, c = clips[cid]
                    rows.append((stamp, slug, sid, c))
    rows.sort(key=lambda r: r[0], reverse=True)
    out, seen_scenes = [], set()
    for stamp, slug, sid, c in rows:            # spread across scenes and lessons
        if (slug, sid) in seen_scenes:
            continue
        seen_scenes.add((slug, sid)); out.append((slug, sid, c))
        if len(out) >= N:
            break
    return out


def build_sheet(items, path):
    from PIL import Image, ImageDraw
    tiles = []
    for slug, sid, c in items:
        try:
            im = Image.open(io.BytesIO(requests.get(c["thumb"], timeout=60, headers={"User-Agent": UA}).content)).convert("RGB")
        except Exception:
            continue
        im.thumbnail((320, 180))
        tile = Image.new("RGB", (320, 200), (16, 16, 16)); tile.paste(im, (0, 0))
        ImageDraw.Draw(tile).text((4, 184), f"{slug} {sid} ✓ {(c.get('caption') or c.get('title') or '')[:36]}", fill=(230, 230, 230))
        tiles.append(tile)
    if not tiles:
        return False
    cols = 4; rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 322, rows * 202), (0, 0, 0))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * 322, (k // cols) * 202))
    sheet.save(path, quality=85)
    return True


def main():
    state_p = ROOT / "library" / "exemplars.json"
    state = json.load(open(state_p)) if state_p.exists() else {}
    changed = False
    for brand in ("edenrise", "belong"):
        items = recent_approvals(brand)
        ids = [c["id"] for _, _, c in items]
        if state.get(brand, {}).get("clips") == ids and state.get(brand, {}).get("url"):
            print(f"{brand}: unchanged ({len(ids)} approvals)"); continue
        path = pathlib.Path(f"/tmp/exemplars-{brand}.jpg")
        if not build_sheet(items, path):
            print(f"{brand}: no approvals with thumbnails yet"); continue
        url = rm.upload_for_slug("library", f"EXEMPLAR__{brand}__{int(time.time())}.jpg", path)
        if not url:
            print(f"{brand}: upload failed"); continue
        state[brand] = {"url": url, "clips": ids, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "from": [f"{s}/{sid}" for s, sid, _ in items]}
        changed = True
        print(f"{brand}: sheet of {len(ids)} approvals → {url}")
    if changed:
        json.dump(state, open(state_p, "w"), indent=1)


if __name__ == "__main__":
    main()
