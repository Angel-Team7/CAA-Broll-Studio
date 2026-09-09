#!/usr/bin/env python3
"""Recall v2 — stage candidates for a beat from its SHOT LIST, for the judge to rank.

    shots (card)  →  per-source phrasings  →  ~150 candidates, metadata only
                  →  cheap text pre-score against the shots, rejected ledger, seen keys
                  →  shortlist STAGE_N (24)  →  preview + thumb + 3-frame strip, uploaded
                  →  appended to the card with judged:false, shown:false
The judge routine (fired by the push) looks at the strips and ranks them.
Beats with no shot list fall back to topup_bot.run_scene.
"""
import json, os, re, sys, time, pathlib, tempfile, subprocess
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import topup_bot as tb          # sources, filters, preview builder
import release_media

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAGE_N = int(os.environ.get("STAGE_N", "24"))
SOURCE_CAP = {"pexels": 14, "pixabay": 8, "coverr": 6}
PAGES = {"pexels": 2, "pixabay": 1, "coverr": 1}
MAX_DURATION = 60
STOP = set("the a an and or of to in on at for with from by is are be this that these those it its as into over under about".split())


def toks(s):
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower()) if w not in STOP}


def pexels_title(c):
    """Pexels sends no title; its page address is one ("man-talking-his-coworkers-3253417")."""
    if c.get("title"):
        return c["title"]
    m = re.search(r"/video/([^/]+?)-\d+/?$", c.get("page_url") or "")
    return m.group(1).replace("-", " ") if m else ""


def rejected_keys():
    p = ROOT / "library" / "rejected.json"
    return set(json.load(open(p)).keys()) if p.exists() else set()


def shot_order(scene, direction):
    """Shots with the fewest clips already on the card go first — a Direction is
    wrong click moves to the shots not yet tried."""
    shots = list(scene.get("shots") or [])
    if not direction:
        return shots
    counts = {}
    for c in scene.get("clips", []):
        counts[c.get("shot", "")] = counts.get(c.get("shot", ""), 0) + 1
    return sorted(shots, key=lambda s: counts.get(s["id"], 0))


def pre_score(c, shot, all_shots, avoid, rank):
    """Cheap, honest text score. The judge does the real ranking on frames."""
    t = toks(c.get("title")) | toks(c.get("query"))
    s = 0.0
    s += 3.0 * len(t & toks(shot["text"]))
    s += 1.0 * len(t & set().union(*(toks(x["text"]) for x in all_shots)))
    if c["source"] == "pexels":
        s += 2.0                         # Pexels search is semantic; its order means something
    s -= 0.15 * rank                     # earlier in the result page = better
    if avoid and (t & set(avoid)):
        s -= 6.0
    if c.get("duration") and c["duration"] < 4:
        s -= 2.0
    return s


def make_strip(preview, strip):
    """Three frames across the preview, tiled 3×1 — what the judge looks at."""
    r = tb.sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(preview))
    try:
        dur = max(1.0, float((r.stdout or "1").strip()))
    except Exception:
        dur = 10.0
    step = max(0.5, dur / 3.2)
    tb.sh("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(preview),
          "-vf", f"fps=1/{step:.3f},scale=426:-2,tile=3x1", "-frames:v", "1", "-q:v", "4", str(strip))
    return strip.exists() and strip.stat().st_size > 5_000


def stage_scene(slug, scene_id, note, profile, reason="", auto_avoid=None):
    card_path = ROOT / "projects" / slug / "scenes.json"
    if not card_path.exists():
        return None                                   # caller reports the missing card
    card = json.load(open(card_path))
    scene = next((s for s in card["scenes"] if s["id"] == scene_id), None)
    if scene is None or not scene.get("shots"):
        return None                                   # caller falls back to run_scene
    direction = reason == "direction"
    want, avoid = tb.parse_note(note)
    avoid = list(dict.fromkeys(avoid + [w for w in (auto_avoid or []) if w]))
    seen = tb.seen_keys(card)
    rejected = rejected_keys()
    shots = shot_order(scene, direction)
    must_not = [m.lower() for m in scene.get("must_not") or []]
    print(f"  recall v2: {len(shots)} shots, direction={direction}, chase={want or '-'}, avoid={avoid or '-'}")

    # ---- recall: metadata only ----------------------------------------------------
    cands, tried = [], set()
    srcs = {"pexels": tb.search_pexels, "pixabay": tb.search_pixabay, "coverr": tb.search_coverr}
    for shot in shots:
        queries = {"pexels": shot["pexels"], "pixabay": shot["pixabay"], "coverr": shot["pexels"]}
        if want:                                         # the reviewer's own words lead
            queries["pexels"] = f"{want[0]} {shot['pexels']}"[:80]
        for name, fn in srcs.items():
            for page in range(1, PAGES[name] + 1):
                try:
                    res = fn(queries[name], page)
                except Exception as e:
                    print(f"    {name} failed: {str(e)[:60]}"); res = []
                for rank, c in enumerate(res):
                    key = f"{c['source']}:{c['src_id']}"
                    purl = (c.get("page_url") or "").rstrip("/")
                    if key in tried or key in seen or (purl and purl in seen) or key in rejected:
                        continue
                    tried.add(key)
                    c["title"] = pexels_title(c) if c["source"] == "pexels" else (c.get("title") or "")
                    desc = f"{c['title']} {c.get('query', '')}"
                    if tb.blocked(desc, profile):
                        continue
                    if any(m and m in desc.lower() for m in must_not):
                        continue
                    if c.get("duration") and c["duration"] > MAX_DURATION:
                        continue
                    c["shot"] = shot["id"]
                    c["_score"] = pre_score(c, shot, shots, avoid, rank)
                    cands.append(c)
    print(f"  recalled {len(cands)} candidates from {len(shots)} shots")
    if not cands:
        return 0

    # ---- shortlist: best score, spread across shots and sources -------------------
    cands.sort(key=lambda c: -c["_score"])
    picks, per_src, per_shot = [], {}, {}
    per_shot_cap = max(4, STAGE_N // max(1, len(shots)) + 2)
    for c in cands:
        if len(picks) >= STAGE_N:
            break
        if per_src.get(c["source"], 0) >= SOURCE_CAP.get(c["source"], 4):
            continue
        if per_shot.get(c["shot"], 0) >= per_shot_cap:
            continue
        picks.append(c)
        per_src[c["source"]] = per_src.get(c["source"], 0) + 1
        per_shot[c["shot"]] = per_shot.get(c["shot"], 0) + 1
    print(f"  shortlisted {len(picks)}: " + ", ".join(f"{k}={v}" for k, v in per_src.items()))

    # ---- stage: preview + thumb + strip, uploaded; on the card unjudged ------------
    idx = tb.next_index(scene, "V")
    added, credits = 0, []
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        for c in picks:
            stem = f"{slug}-{scene_id}-V{idx:02d}"
            idx += 1
            master = td / f"{stem}.src.mp4"
            try:
                with requests.get(c["download_url"], stream=True, timeout=90, headers={"User-Agent": tb.UA}) as r:
                    r.raise_for_status()
                    with open(master, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
            except Exception as e:
                print(f"    download failed ({c['source']} {c['src_id']}): {str(e)[:70]}"); continue
            if master.stat().st_size < 100_000:
                continue
            pv, th, st = td / f"{stem}.mp4", td / f"{stem}.jpg", td / f"{stem}.strip.jpg"
            if not tb.make_preview(master, pv, th):
                continue
            if not make_strip(pv, st):
                print(f"    strip failed for {stem}"); continue
            pv_url = release_media.upload_for_slug(slug, release_media.asset_name(scene_id, "preview", pv), pv)
            th_url = release_media.upload_for_slug(slug, release_media.asset_name(scene_id, "thumb", th), th)
            st_url = release_media.upload_for_slug(slug, release_media.asset_name(scene_id, "strip", st), st)
            if not (pv_url and th_url and st_url):
                print(f"    upload failed for {stem}"); continue
            scene.setdefault("clips", []).append({
                "id": stem, "type": "video", "source": c["source"], "author": c.get("author", ""),
                "license": c.get("license", ""), "page_url": c.get("page_url", ""),
                "thumb": th_url, "preview": pv_url, "strip": st_url,
                "title": c.get("title", ""), "query": c.get("query", ""), "shot": c.get("shot", ""),
                "duration": c.get("duration", 0), "src_id": c.get("src_id", ""),
                "download_url": c.get("download_url", ""),
                "fresh": True, "added_by": "recall-v2", "staged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "judged": False, "shown": False,
            })
            credits.append(tb.credit_line(c))
            master.unlink(missing_ok=True); pv.unlink(missing_ok=True)
            added += 1
    if added:
        json.dump(card, open(card_path, "w"), indent=1, ensure_ascii=False)
        cf = ROOT / "projects" / slug / "CREDITS.md"
        if not cf.exists():
            cf.write_text(f"# Credits — {slug}\n\n| source | title | author | license | page |\n|---|---|---|---|---|\n")
        with open(cf, "a") as fh:
            fh.write("\n".join(credits) + "\n")
    print(f"  staged {added} candidates for {slug} {scene_id} (awaiting judge)")
    return added


if __name__ == "__main__":
    slug, sid = sys.argv[1], sys.argv[2]
    note = sys.argv[3] if len(sys.argv) > 3 else ""
    n = stage_scene(slug, sid, note, "belong" if slug.startswith("belong") else "edenrise",
                    reason=("direction" if "--direction" in sys.argv else ""))
    print("STAGED", n)
