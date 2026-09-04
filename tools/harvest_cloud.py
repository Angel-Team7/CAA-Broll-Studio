#!/usr/bin/env python3
"""Scheduled stocking job — runs on GitHub Actions, no Mac involved.

Instead of searching when someone clicks, this searches ahead of time. Every beat
on every cockpit card is a theme; for each theme that is thin in the owned library
it fetches a few fresh candidates, builds 480p previews, uploads them to the
shared `media-library` release, and appends them to library/index.json with the
same director facets the cards use. A later click then promotes off the shelf
instead of hitting the internet.

Guards: taste filter (blocked / has_signal), dedupe on source:id and page_url
against everything already owned, per-run budget so a cron tick stays short,
and masters are never stored — only 480p previews + metadata.
"""
import json, os, pathlib, sys, tempfile, time, re
import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import release_media as rm                                   # noqa: E402
from build_library import classify, toks                     # noqa: E402
import topup_bot as tb                                       # noqa: E402

ROOT = HERE.parent
LIB_PATH = ROOT / "library" / "index.json"
LIB_SLUG = "library"                                         # release tag: media-library
BUDGET = int(os.environ.get("HARVEST_BUDGET", "30"))        # new clips per run
THIN_AT = int(os.environ.get("HARVEST_THIN_AT", "12"))      # themes with fewer owned videos get stocked
PER_THEME = int(os.environ.get("HARVEST_PER_THEME", "3"))

def themes():
    """One theme per distinct beat across all cards, with brand and sample words."""
    seen, out = set(), []
    for card in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = card.parent.name
        brand = "belong" if slug.startswith("belong") else "edenrise"
        try: data = json.load(open(card))
        except Exception: continue
        for sc in data.get("scenes", []):
            vd = (sc.get("visual_direction") or "").strip()
            if len(vd) < 20: continue
            key = re.sub(r"\W+", " ", vd.lower())[:80]
            if key in seen: continue
            seen.add(key)
            out.append({"brand": brand, "direction": vd,
                        "queries": [q for q in (c.get("query") for c in sc.get("clips", [])) if q][:6]})
    return out

def owned_for(theme, lib):
    want = classify({"title": theme["direction"], "query": " ".join(theme["queries"])}, theme["brand"])
    n = 0
    for a in lib:
        if a.get("type") != "video": continue
        if set(a.get("actions", [])) & set(want["actions"]) and set(a.get("subjects", [])) & set(want["subjects"]):
            n += 1
    return n

def main():
    lib = json.load(open(LIB_PATH))
    assets = lib["assets"]
    seen = {a["key"] for a in assets} | {(a.get("page_url") or "").rstrip("/") for a in assets}
    tag, rel_id = rm.ensure_release(LIB_SLUG)
    ths = themes()
    thin = [t for t in ths if owned_for(t, assets) < THIN_AT]
    print(f"themes: {len(ths)} | thin (<{THIN_AT} owned videos): {len(thin)} | budget {BUDGET}")
    added, credits = 0, []
    with tempfile.TemporaryDirectory() as td:
        for t in thin:
            if added >= BUDGET: break
            qs = t["queries"] or tb.queries_for({"visual_direction": t["direction"], "clips": []}, "")
            got = 0
            for q in qs:
                if got >= PER_THEME or added >= BUDGET: break
                for src in tb.SOURCES:
                    if got >= PER_THEME: break
                    for c in src(q, 2):
                        if got >= PER_THEME or added >= BUDGET:
                            break                 # budgets must bind inside the result loop too
                        key = f"{c['source']}:{c['src_id']}"; purl = (c.get("page_url") or "").rstrip("/")
                        if key in seen or (purl and purl in seen): continue
                        desc = (c.get("title") or "").strip()
                        if tb.blocked(f"{desc} {q}", t["brand"]): continue
                        if desc and not tb.has_signal(desc): continue
                        if c.get("duration") and c["duration"] > 180: continue
                        seen.add(key); seen.add(purl)
                        stem = f"lib-{c['source']}-{c['src_id']}"
                        master = pathlib.Path(td) / f"{stem}.mp4"
                        try:
                            with requests.get(c["download_url"], stream=True, timeout=90,
                                              headers={"User-Agent": tb.UA}) as r:
                                r.raise_for_status()
                                with open(master, "wb") as fh:
                                    for chunk in r.iter_content(1 << 20): fh.write(chunk)
                        except Exception as e:
                            print(f"  ! download {c['source']}: {str(e)[:60]}"); continue
                        if master.stat().st_size < 100_000: continue
                        pv, th = master.with_name(f"{stem}.pv.mp4"), master.with_name(f"{stem}.jpg")
                        if not tb.make_preview(master, pv, th): continue
                        pv_url = rm.upload(rel_id, rm.asset_name("LIB", "preview", pv), pv)
                        th_url = rm.upload(rel_id, rm.asset_name("LIB", "thumb", th), th)
                        if not (pv_url and th_url): continue
                        row = {"key": key, "source": c["source"], "src_id": c["src_id"],
                               "page_url": c.get("page_url", ""), "type": "video",
                               "title": desc, "query": q, "author": c.get("author", ""),
                               "license": c["license"], "download_url": c["download_url"],
                               "preview": pv_url, "thumb": th_url, "used_in": [],
                               "harvested": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "theme": t["direction"][:120]}
                        row.update(classify({"title": desc, "query": q}, t["brand"]))
                        assets.append(row); credits.append(tb.credit_line(c))
                        got += 1; added += 1
                        print(f"  + [{t['brand']}] {desc[:48] or q}  ← {t['direction'][:40]}")
                        master.unlink(missing_ok=True); pv.unlink(missing_ok=True); th.unlink(missing_ok=True)
    if added:                                   # a zero run must not churn the index
        lib["count"] = len(assets); lib["generated"] = "harvest_cloud.py"
        json.dump(lib, open(LIB_PATH, "w"), separators=(",", ":"))
    if credits:
        cf = ROOT / "library" / "CREDITS.md"
        if not cf.exists():
            cf.write_text("# Credits — shared library\n\n| source | title | author | license | page |\n|---|---|---|---|---|\n")
        with open(cf, "a") as fh: fh.write("\n".join(credits) + "\n")
    print(f"HARVESTED={added}  library now {len(assets)} assets")

if __name__ == "__main__":
    main()
