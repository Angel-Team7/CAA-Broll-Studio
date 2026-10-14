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
import collections, json, os, shutil, subprocess, pathlib, sys, tempfile, time, re
from itertools import zip_longest

import requests

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import release_media as rm                                   # noqa: E402
from build_library import classify, toks                     # noqa: E402
import topup_bot as tb                                       # noqa: E402
import sectors                                               # noqa: E402

ROOT = HERE.parent
LIB_PATH = ROOT / "library" / "index.json"
LIB_SLUG = "library"                                         # release tag: media-library
BUDGET = int(os.environ.get("HARVEST_BUDGET", "30"))        # new clips per run
THIN_AT = int(os.environ.get("HARVEST_THIN_AT", "12"))      # themes with fewer owned videos get stocked
PER_THEME = int(os.environ.get("HARVEST_PER_THEME", "3"))
PAGE_SWEEP = int(os.environ.get("HARVEST_PAGE_SWEEP", "8"))  # runs sweep result pages 2..9

def themes():
    """One theme per distinct beat across all cards, with its sector and sample words."""
    seen, out = set(), []
    for card in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = card.parent.name
        brand = sectors.for_slug(slug)
        try: data = json.load(open(card))
        except Exception: continue
        for sc in data.get("scenes", []):
            vd = (sc.get("visual_direction") or "").strip()
            shots = sc.get("shots") or []
            if shots:
                # Phase 3: the harvester searches the beat's SHOT LIST, not word chunks
                vd = "; ".join(sh["text"] for sh in shots)
                queries = [sh["pexels"] for sh in shots]
            else:
                if len(vd) < 20: continue
                queries = [q for q in (c.get("query") for c in sc.get("clips", [])) if q][:6]
            key = re.sub(r"\W+", " ", vd.lower())[:80]
            if key in seen: continue
            seen.add(key)
            out.append({"brand": brand, "direction": vd, "queries": queries})

    # Cards come first — a real lesson's beats are the truest demand signal. Then every
    # sector's seed beats, so a sector with no cards at all (a new client, a new
    # department) still gets stocked by the hourly run instead of waiting for its first
    # lesson to be written.
    for sid, cfg in sectors.all_sectors().items():
        for seed in cfg.get("seeds") or []:
            key = re.sub(r"\W+", " ", seed.lower())[:80]
            if key in seen:
                continue
            seen.add(key)
            out.append({"brand": sid, "direction": seed, "queries": [seed], "seed": True})
    return out

def owned_for(theme, lib):
    want = classify({"title": theme["direction"], "query": " ".join(theme["queries"])}, theme["brand"])
    n = 0
    for a in lib:
        if a.get("dead"): continue
        if a.get("type") != "video": continue
        if set(a.get("actions", [])) & set(want["actions"]) and set(a.get("subjects", [])) & set(want["subjects"]):
            n += 1
    return n

def _log(ths, thin, assets, added, sick=""):
    """One line per run so the week's stocking can be tracked without reading Actions logs."""
    brands = {}
    for a in assets[-added:] if added else []:
        k = a.get("sector") or a.get("brand") or "?"
        brands[k] = brands.get(k, 0) + 1
    with open(ROOT / "library" / "harvest_log.jsonl", "a") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                             "added": added, "themes": len(ths), "thin": len(thin),
                             "library": len(assets), "by_sector": brands,
                             "by_brand": brands, "sources": sick or "ok"}) + "\n")


def main():
    # A contradictory sector entry does not crash a gather, it quietly wastes one: the
    # harvester shops for footage the same sector's never-list then throws away. Refuse
    # to spend a budget on a broken registry. (Workflow files need a token scope this bot
    # does not have, so the guard lives here rather than as a workflow step.)
    chk = subprocess.run([sys.executable, str(ROOT / "tools" / "verify" / "sector_law.py")],
                         capture_output=True, text=True)
    if chk.returncode:
        print(chk.stdout[-2000:] or chk.stderr[-2000:])
        print("! sector registry is not sound — harvest aborted")
        return
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("::error::ffmpeg/ffprobe are not on PATH — every preview would fail and the "
              "run would add nothing while reporting success. Check the 'Cache ffmpeg' and "
              "'Install deps' steps; the cache may have been evicted.")
        sys.exit(1)
    lib = json.load(open(LIB_PATH))
    assets = lib["assets"]
    seen = {a["key"] for a in assets} | {(a.get("page_url") or "").rstrip("/") for a in assets}
    tag, rel_id = rm.ensure_release(LIB_SLUG)
    ths = themes()
    thin = [t for t in ths if owned_for(t, assets) < THIN_AT]

    # Two starvation traps, both fixed here.
    #
    # 1. A budget of 30 spent down a fixed list means the first themes are shopped every
    #    hour forever and the tail is never reached — a thin theme does not stop being
    #    thin after 3 clips. So the list is ROTATED by the number of runs so far: each run
    #    starts where the last one left off and the whole list gets served over a day.
    # 2. Real lessons' beats and sector seeds compete for the same budget, and there are
    #    always more thin lesson beats than a run can hold — seeds would never get a
    #    single clip. So they are INTERLEAVED: a run stocks lessons and new sectors both.
    # The rotation counter CANNOT come from the run log alone: that file is only committed
    # when a run adds something, so a run of zero leaves the count unchanged, the next run
    # picks the same themes and the same result page, adds zero again, and the harvester
    # deadlocks on one page forever. That is exactly what three weeks of green empty runs
    # were. Wall-clock advances whether or not anything was committed, so mix it in.
    runs = 0
    log_p = ROOT / "library" / "harvest_log.jsonl"
    if log_p.exists():
        runs = sum(1 for _ in open(log_p))
    runs += int(time.time() // 3600)        # advances every hour, committed or not
    cards = [t for t in thin if not t.get("seed")]
    seeds_t = [t for t in thin if t.get("seed")]
    # Step by what a run actually consumes — half its themes from each list — or the
    # rotation crawls behind the budget and every run re-serves the same beats.
    step = max(1, (BUDGET // max(1, PER_THEME)) // 2)
    for lst in (cards, seeds_t):
        if lst:
            off = (runs * step) % len(lst)
            lst[:] = lst[off:] + lst[:off]
    thin = [t for pair in zip_longest(cards, seeds_t) for t in pair if t]
    nseed = sum(1 for t in thin if t.get("seed"))
    # Page 2 of a theme is exhausted the moment we own it. Advance with the run counter so
    # the search walks further into the results each time instead of re-reading one page.
    page = 2 + (runs % PAGE_SWEEP)
    print(f"themes: {len(ths)} ({sum(1 for t in ths if t.get('seed'))} sector seeds) | "
          f"thin (<{THIN_AT} owned videos): {len(thin)} of which {nseed} seeds | "
          f"run #{runs + 1}, rotated by {step}, page {page} | budget {BUDGET}")
    added, credits = 0, []
    looked = dupes = 0
    lost = collections.Counter()
    with tempfile.TemporaryDirectory() as td:
        for t in thin:
            if added >= BUDGET: break
            qs = t["queries"] or tb.queries_for({"visual_direction": t["direction"], "clips": []}, "")
            got = 0
            for q in qs:
                if got >= PER_THEME or added >= BUDGET: break
                for src in tb.SOURCES:
                    if got >= PER_THEME: break
                    for c in src(q, page):
                        if got >= PER_THEME or added >= BUDGET:
                            break                 # budgets must bind inside the result loop too
                        key = f"{c['source']}:{c['src_id']}"; purl = (c.get("page_url") or "").rstrip("/")
                        looked += 1
                        if key in seen or (purl and purl in seen):
                            dupes += 1
                            continue
                        desc = (c.get("title") or "").strip()
                        if tb.blocked(f"{desc} {q}", t["brand"]): continue
                        if desc and not tb.has_signal(desc, t["brand"]): continue
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
                            print(f"  ! download {c['source']}: {str(e)[:60]}")
                            lost["download"] += 1; continue
                        if master.stat().st_size < 100_000:
                            lost["tiny download"] += 1; continue
                        pv, th = master.with_name(f"{stem}.pv.mp4"), master.with_name(f"{stem}.jpg")
                        if not tb.make_preview(master, pv, th):
                            lost["preview/ffmpeg"] += 1; continue
                        pv_url = rm.upload_for_slug(LIB_SLUG, rm.asset_name("LIB", "preview", pv), pv)
                        th_url = rm.upload_for_slug(LIB_SLUG, rm.asset_name("LIB", "thumb", th), th)
                        if not (pv_url and th_url):
                            lost["release upload"] += 1; continue
                        row = {"key": key, "source": c["source"], "src_id": c["src_id"],
                               "page_url": c.get("page_url", ""), "type": "video",
                               "title": desc, "query": q, "author": c.get("author", ""),
                               "license": c["license"], "download_url": c["download_url"],
                               "preview": pv_url, "thumb": th_url, "used_in": [],
                               "harvested": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "theme": t["direction"][:120], "sector": t["brand"]}
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

    # A green run that stocked nothing is the failure mode that hid a two-week outage:
    # the stock keys stopped answering, every source returned an empty list, and the run
    # exited 0 with "HARVESTED=0" looking exactly like "the shelf is full". If there was
    # work to do and a source is not answering, say so and FAIL, so it shows up red.
    sick = tb.health_report()
    if sick:
        print(f"! sources not answering — {sick}")
    if lost:
        worst, n = lost.most_common(1)[0]
        print(f"candidates lost on the way in: {dict(lost)}")
        if added == 0 and n >= 5:
            print(f"::error::{n} candidate(s) were found and then lost at '{worst}'. The "
                  f"search is working; the failure is downstream of it.")
            _log(ths, thin, assets, added, f"lost at {worst}: {n}")
            sys.exit(1)
    if added == 0 and thin:
        print(f"! {len(thin)} theme(s) still need stock and this run added nothing.")
        if sick:
            print("::error::harvest stocked nothing because the stock sources are not "
                  f"answering — {sick}. Check the repo secrets PEXELS_API_KEY, "
                  "PIXABAY_API_KEY and COVERR_API_KEY (expired, revoked or out of quota).")
            _log(ths, thin, assets, added, sick)
            sys.exit(1)
        if looked and dupes / looked > 0.9:
            print(f"  exhausted: {dupes} of {looked} results on page {page} are already on "
                  f"the shelf. The sources are healthy — this sweep has simply been read. "
                  f"Raise HARVEST_PAGE_SWEEP or give the thin themes new phrasings.")
        else:
            print(f"  (sources answered normally; {dupes} of {looked} results were already "
                  f"owned, so the thin themes genuinely had no new hits)")
    _log(ths, thin, assets, added, sick)


if __name__ == "__main__":
    main()
