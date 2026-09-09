#!/usr/bin/env python3
"""The shared library was indexed before previews moved to Releases, so 2,420 of its
assets still point at local paths that no longer exist — and library-first copied a few
of those onto cards. Rewrite every asset to the URL the Release actually serves:
first via the card clip it is used in, then via the Release asset map, else mark it dead.

    python3 tools/fix_library_urls.py
"""
import json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release_media as rm

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "library" / "index.json"


def norm(name):
    return re.sub(r"\.{2,}", ".", name)


def main():
    lib = json.load(open(LIB))
    cards = {p.parent.name: json.load(open(p)) for p in (ROOT / "projects").glob("*/scenes.json")}
    by_clip = {}
    for slug, card in cards.items():
        for s in card["scenes"]:
            for c in s["clips"]:
                by_clip[(slug, s["id"], c["id"])] = c
    maps = {}

    def release_map(slug):
        if slug not in maps:
            try:
                _, rid = rm.ensure_release(slug)
                maps[slug] = {norm(k): v for k, v in rm.asset_urls(rid).items()}
            except Exception as e:
                print(f"  ! release map for {slug}: {e}"); maps[slug] = {}
        return maps[slug]

    fixed = dead = 0
    for a in lib["assets"]:
        if str(a.get("preview", "")).startswith("http") and str(a.get("thumb", "")).startswith("http"):
            continue
        done = False
        for u in a.get("used_in") or []:
            c = by_clip.get((u.get("project"), u.get("scene"), u.get("clip_id")))
            if c and str(c.get("preview", "")).startswith("http"):
                a["preview"], a["thumb"] = c["preview"], c.get("thumb", c["preview"]); done = True; break
        if not done:
            m = re.match(r"projects/([^/]+)/previews/([^/]+)/(.+)$", str(a.get("preview", "")))
            if m:
                slug, scene, fn = m.groups()
                amap = release_map(slug)
                pv = amap.get(norm(f"{scene}__preview__{fn}"))
                th = amap.get(norm(f"{scene}__thumb__{pathlib.Path(fn).stem}.jpg"))
                if pv:
                    a["preview"], a["thumb"] = pv, th or pv; done = True
        if done:
            a.pop("dead", None); fixed += 1
        else:
            a["dead"] = True; dead += 1
    json.dump(lib, open(LIB, "w"), separators=(",", ":"))
    # cards: any clip still on a local path gets the same treatment
    cfixed = cdrop = 0
    for slug, card in cards.items():
        changed = False
        for s in card["scenes"]:
            keep = []
            for c in s["clips"]:
                if str(c.get("preview", "")).startswith("http"):
                    keep.append(c); continue
                m = re.match(r"projects/([^/]+)/previews/([^/]+)/(.+)$", str(c.get("preview", "")))
                pv = th = None
                if m:
                    oslug, scene, fn = m.groups()
                    amap = release_map(oslug)
                    pv = amap.get(norm(f"{scene}__preview__{fn}"))
                    th = amap.get(norm(f"{scene}__thumb__{pathlib.Path(fn).stem}.jpg"))
                if pv:
                    c["preview"], c["thumb"] = pv, th or pv; keep.append(c); cfixed += 1
                else:
                    cdrop += 1
                changed = True
            s["clips"] = keep
        if changed:
            json.dump(card, open(ROOT / "projects" / slug / "scenes.json", "w"), indent=1, ensure_ascii=False)
    print(f"library: {fixed} fixed, {dead} marked dead | cards: {cfixed} fixed, {cdrop} dropped (no file anywhere)")


if __name__ == "__main__":
    main()
