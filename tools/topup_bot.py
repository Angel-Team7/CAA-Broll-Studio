#!/usr/bin/env python3
"""Search-10-more bot — runs on GitHub Actions when the cockpit records a top-up request.

Reads selections/*.json, finds topup_requests where done=false, fetches fresh
royalty-free VIDEO candidates for that scene, builds 480p previews + thumbs, and
appends them to the card's scenes.json.

Masters are never committed: each clip keeps source/page_url/src_id/download_url
so the full-resolution file is re-fetchable by id at render time.

Deliberately raw: no vision curation happens here (that is a human/Claude pass).
A taste blocklist removes the junk classes we keep hitting — end-cards, cartoons,
green screen, wildlife, sewing factories, corporate/office stock.
"""
import json, os, pathlib, re, subprocess, sys, tempfile, time
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_library import classify, toks, VOCAB, facet, SCALE, PEOPLE

LIBRARY_MAX_SHARE = float(os.environ.get("TOPUP_LIBRARY_SHARE", "0.4"))
LIBRARY_URL = os.environ.get(
    "LIBRARY_URL",
    "https://raw.githubusercontent.com/Angel-Team7/CAA-Broll-Studio/main/library/index.json")


def load_library():
    """The stock we already own. Reusing one of these costs no download and no
    transcode — its preview is already committed to this repo."""
    local = ROOT / "library" / "index.json"
    try:
        if local.exists():
            return json.load(open(local))["assets"]
        r = requests.get(LIBRARY_URL, timeout=60)
        r.raise_for_status()
        return r.json()["assets"]
    except Exception as e:
        print(f"  ! library unavailable ({str(e)[:60]}) — going straight to the sources")
        return []


def scene_facets(scene, note):
    qs = " ".join((c.get("query") or "") for c in scene.get("clips", [])[:20])
    text = " ".join([scene.get("visual_direction", ""), scene.get("script_line", ""),
                     note or "", qs])
    t = toks(text)
    return {
        "subjects": facet(t, VOCAB["subjects"]),
        "actions": facet(t, VOCAB["actions"]),
        "setting": facet(t, VOCAB["setting"]),
        "tokens": t,
    }


def library_picks(scene, note, brand, seen, want):
    """Score owned footage against this beat. Facets first (what it shows), then
    raw word overlap as a tiebreak. Anything already on this card is excluded."""
    assets = load_library()
    if not assets:
        return []
    want_f = scene_facets(scene, note)
    scored = []
    for a in assets:
        if a.get("type") != "video":
            continue
        if a["key"] in seen or (a.get("page_url") or "").rstrip("/") in seen:
            continue
        if not a.get("preview"):
            continue
        if blocked(f"{a.get('title','')} {a.get('query','')}", brand):
            continue
        act_hits = len(set(a.get("actions", [])) & set(want_f["actions"]))
        if not act_hits:
            continue            # the VERB is the meaning. Matching "worker + site"
                                # without it is how generic footage gets in.
        sc = 0
        sc += 3 * len(set(a.get("subjects", [])) & set(want_f["subjects"]))
        sc += 4 * act_hits
        sc += 2 * len(set(a.get("setting", [])) & set(want_f["setting"]))
        facet_hits = sc                   # subjects/actions/setting only, so far
        sc += min(6, len(set(a.get("tags", [])) & want_f["tokens"]))
        if a.get("brand") == brand:
            sc += 1                       # same client's world, gentle preference
        used = len(a.get("used_in", []))
        sc -= min(3, max(0, used - 1))     # spread the load; no clip everywhere
        # must genuinely depict the beat, not merely share vocabulary
        if facet_hits >= 5 and sc >= 8:
            scored.append((sc, a))
    scored.sort(key=lambda x: -x[0])
    return [a for _, a in scored[:want]]


ROOT = pathlib.Path(os.environ.get("TOPUP_ROOT")
                    or pathlib.Path(__file__).resolve().parent.parent)
TIMEOUT = 30
UA = "CAA-Broll-Studio-Bot/1.0 (+https://github.com/Angel-Team7/CAA-Broll-Studio)"
WANT_VIDEOS = int(os.environ.get("TOPUP_VIDEOS", "10"))
PREVIEW_SECONDS = os.environ.get("TOPUP_PREVIEW_SECONDS", "20")
MAX_SCENES_PER_RUN = int(os.environ.get("TOPUP_MAX_SCENES", "8"))

# ---------------------------------------------------------------- taste filter
# Matching is WORD-BOUNDED on purpose: substring matching let "german" satisfy
# "man" and "handmade" satisfy "hand", which is how wheat fields and a dog got in.
def _tok(text):
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        out.add(w)
        if len(w) > 3 and w.endswith("s"):
            out.add(w[:-1])          # insects -> insect, bees -> bee
    return out

JUNK = {
    # platform / template junk
    "subscribe", "outro", "intro", "template", "greenscreen", "chroma", "logo",
    "watermark", "placeholder", "mockup", "cartoon", "animated", "render", "clipart",
    # abstract / texture filler
    "bokeh", "macro", "texture", "bubble", "abstract", "gradient", "fractal",
    "neon", "glitter", "particle", "smoke", "ink", "wallpaper", "screensaver",
    # nature / scenery with no work in it
    "underwater", "ocean", "sea", "wave", "waves", "river", "lake", "waterfall",
    "sky", "cloud", "clouds", "sunset", "sunrise", "beach", "mountain", "forest",
    "grass", "leaf", "leaves", "flower", "flowers", "blossom", "rose", "sunflower",
    "thistle", "wheat", "aurora", "snow", "rain", "storm",
    # animals
    "dog", "cat", "pet", "puppy", "kitten", "animal", "wildlife", "bird", "birds",
    "woodpecker", "insect", "bee", "bees", "butterfly", "fish", "salamander",
    "squirrel", "deer", "fauna",
}
JUNK_PHRASES = ("thanks for watching", "thank you for watching", "no copyright",
                "free download", "lower third", "green screen", "stock footage")

EDENRISE_BLOCK = {
    "abandoned", "derelict", "ruin", "ruins", "debris", "demolition", "demolished",
    "collapse", "collapsed", "destroyed", "destruction", "graffiti", "vandalism",
    "war", "rubble", "decay", "cube", "geometric", "minimalist",
    "sewing", "seamstress", "textile", "businessman", "businesswoman", "boardroom",
    "startup", "laptop", "office", "medical", "doctor", "nurse", "hospital",
    "massage", "yoga", "gym", "wedding", "romantic", "kiss", "cocktail", "makeup",
    "model", "fashion", "casino", "gaming",
}
BELONG_BLOCK = {
    "businessman", "boardroom", "hospital", "gym", "casino", "nightclub",
    "skyscraper", "traffic", "factory",
}

# a candidate must show a person, their hands, or their work — not a mood
POSITIVE = {
    "worker", "workers", "man", "men", "woman", "women", "people", "person",
    "guy", "lady", "hand", "hands", "builder", "builders",
    "construction", "site", "labour", "labor", "tool", "tools", "craft",
    "craftsman", "artisan", "carpenter", "carpentry", "mason", "masonry", "brick",
    "bricks", "wood", "woodwork", "timber", "concrete", "cement", "mortar",
    "trowel", "shovel", "drill", "hammer", "saw", "welder", "welding", "garden",
    "gardener", "gardening", "farm", "farmer", "farming", "harvest", "vineyard",
    "olive", "landscaping", "plaster", "plastering", "painter", "painting",
    "repair", "install", "installation", "renovation", "team", "teamwork",
    "colleague", "colleagues", "crew", "apprentice", "training", "workshop",
    "helmet", "hardhat", "vest", "engineer", "foreman", "supervisor", "chef",
    "kitchen", "hotel", "waiter", "kneading", "serving", "tiling", "tiles",
}

def blocked(text, profile):
    low = (text or "").lower()
    if any(ph in low for ph in JUNK_PHRASES):
        return True
    toks = _tok(text)
    if toks & JUNK:
        return True
    return bool(toks & (BELONG_BLOCK if profile == "belong" else EDENRISE_BLOCK))

def has_signal(text):
    return bool(_tok(text) & POSITIVE)

# ------------------------------------------------------------------- sources
def _cand(**kw):
    kw.setdefault("title", "")
    kw.setdefault("author", "")
    kw.setdefault("duration", 0)
    return kw

def search_pexels(query, page):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    out = []
    try:
        r = requests.get("https://api.pexels.com/videos/search",
                         params={"query": query, "per_page": 15, "page": page,
                                 "orientation": "landscape"},
                         headers={"Authorization": key, "User-Agent": UA}, timeout=TIMEOUT)
        for v in r.json().get("videos", []):
            files = sorted(v.get("video_files", []), key=lambda f: (f.get("width") or 0), reverse=True)
            best = next((f for f in files if (f.get("height") or 0) <= 1080), files[0] if files else None)
            if not best:
                continue
            out.append(_cand(source="pexels", src_id=str(v["id"]),
                             download_url=best["link"], page_url=v["url"],
                             author=v.get("user", {}).get("name", ""),
                             license="Pexels License", license_url="https://www.pexels.com/license/",
                             duration=v.get("duration", 0), query=query,
                             title=(v.get("alt") or "").strip()))
    except Exception as e:
        print(f"  ! pexels: {e}")
    return out

def search_pixabay(query, page):
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        return []
    out = []
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": key, "q": query, "per_page": 20, "page": page,
                                 "safesearch": "true"},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
        for v in r.json().get("hits", []):
            vids = v.get("videos", {})
            best = vids.get("large") or vids.get("medium") or vids.get("small")
            if not best or not best.get("url"):
                continue
            out.append(_cand(source="pixabay", src_id=str(v["id"]),
                             download_url=best["url"],
                             page_url=v.get("pageURL", ""),
                             author=v.get("user", ""),
                             license="Pixabay Content License",
                             license_url="https://pixabay.com/service/license-summary/",
                             duration=v.get("duration", 0), query=query,
                             title=" ".join((v.get("tags") or "").split(",")).strip()))
    except Exception as e:
        print(f"  ! pixabay: {e}")
    return out

def search_coverr(query, page):
    key = os.environ.get("COVERR_API_KEY")
    if not key:
        return []
    out = []
    try:
        r = requests.get("https://api.coverr.co/videos",
                         params={"query": query, "page_size": 20, "page": page, "urls": "true"},
                         headers={"Authorization": f"Bearer {key}", "User-Agent": UA}, timeout=TIMEOUT)
        for v in r.json().get("hits", []):
            url = (v.get("urls") or {}).get("mp4_download") or (v.get("urls") or {}).get("mp4")
            if not url:
                continue
            out.append(_cand(source="coverr", src_id=str(v.get("id")),
                             download_url=url,
                             page_url=f"https://coverr.co/videos/{v.get('slug', v.get('id'))}",
                             author=(v.get("creator") or {}).get("name", "Coverr"),
                             license="Coverr License", license_url="https://coverr.co/license",
                             duration=v.get("duration", 0), query=query,
                             title=v.get("title", "")))
    except Exception as e:
        print(f"  ! coverr: {e}")
    return out

def search_wikimedia(query, page):
    """Keyless fallback so the Action still works before secrets are set."""
    out = []
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php",
                         params={"action": "query", "format": "json", "generator": "search",
                                 "gsrsearch": f'filetype:video {query}', "gsrlimit": 15,
                                 "gsroffset": (page - 1) * 15, "prop": "imageinfo",
                                 "iiprop": "url|size|extmetadata"},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
        for p in (r.json().get("query", {}).get("pages", {}) or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("url")
            if not url or not url.lower().endswith((".webm", ".ogv", ".mp4")):
                continue
            meta = ii.get("extmetadata", {})
            lic = (meta.get("LicenseShortName", {}) or {}).get("value", "")
            if not any(t in lic.lower() for t in ("cc0", "public domain", "cc by", "cc-by")):
                continue
            out.append(_cand(source="wikimedia", src_id=str(p.get("pageid")),
                             download_url=url,
                             page_url=ii.get("descriptionurl", ""),
                             author=re.sub("<[^>]+>", "", (meta.get("Artist", {}) or {}).get("value", ""))[:80],
                             license=lic, license_url=ii.get("descriptionurl", ""),
                             query=query, title=p.get("title", "")))
    except Exception as e:
        print(f"  ! wikimedia: {e}")
    return out

SOURCES = (search_pexels, search_pixabay, search_coverr, search_wikimedia)

# ------------------------------------------------------------------- helpers
def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)

def queries_for(scene, note):
    """Reuse the scene's own proven queries, then widen with its visual direction."""
    seen, qs = set(), []
    for c in scene.get("clips", []):
        q = (c.get("query") or "").strip()
        if q and q.lower() not in seen:
            seen.add(q.lower()); qs.append(q)
    words = re.findall(r"[a-zA-Z]{4,}", (scene.get("visual_direction") or ""))
    STOP = {"then", "that", "with", "this", "their", "them", "from", "into", "over",
            "while", "after", "before", "someone", "something", "person", "people",
            "close", "shot", "shots", "camera", "frame", "plus", "real"}
    key = [w.lower() for w in words if w.lower() not in STOP][:8]
    for i in range(0, max(0, len(key) - 2), 3):
        qs.append(" ".join(key[i:i + 3]))
    for w in re.findall(r"[a-zA-Z]{4,}", note or ""):
        if w.lower() not in STOP and len(qs) < 14:
            qs.append(w.lower())
    fixed = []
    for q in qs[:14]:
        fixed.append(q if has_signal(q) else f"worker {q}")
    return fixed or ["worker hands work"]

def next_index(scene, letter):
    n = -1
    for c in scene.get("clips", []):
        m = re.search(rf"-{letter}(\d+)$", c["id"])
        if m:
            n = max(n, int(m.group(1)))
    return n + 1

def seen_keys(card):
    keys = set()
    for sc in card["scenes"]:
        for c in sc.get("clips", []):
            if c.get("page_url"):
                keys.add(c["page_url"].rstrip("/"))
            if c.get("src_id") and c.get("source"):
                keys.add(f"{c['source']}:{c['src_id']}")
    return keys

def make_preview(master, preview, thumb):
    ok = sh("ffmpeg", "-nostdin", "-v", "error", "-y", "-t", PREVIEW_SECONDS, "-i", str(master),
            "-vf", "scale=854:-2", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "30", "-an", "-movflags", "+faststart", str(preview))
    if not preview.exists() or preview.stat().st_size < 20_000:
        print(f"    preview failed: {ok.stderr.strip()[:120]}")
        return False
    sh("ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", "1", "-i", str(master),
       "-frames:v", "1", "-vf", "scale=480:-1", str(thumb))
    if not thumb.exists():
        sh("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(master),
           "-frames:v", "1", "-vf", "scale=480:-1", str(thumb))
    return True

def credit_line(c):
    return f"| {c['source']} | {c.get('title','')[:60]} | {c.get('author','')} | {c['license']} | {c.get('page_url','')} |"

# ---------------------------------------------------------------------- main
def run_scene(slug, scene_id, note, profile):
    card_path = ROOT / "projects" / slug / "scenes.json"
    if not card_path.exists():
        print(f"  ! no scenes.json for {slug} — skipped")
        return 0
    card = json.load(open(card_path))
    scene = next((s for s in card["scenes"] if s["id"] == scene_id), None)
    if scene is None:
        print(f"  ! {slug} has no scene {scene_id} — skipped")
        return 0

    seen = seen_keys(card)

    # 1) shop our own shelves first — instant, free, and it builds continuity
    from_lib = library_picks(scene, note, profile, seen,
                             max(1, int(WANT_VIDEOS * LIBRARY_MAX_SHARE)))
    need_web = WANT_VIDEOS - len(from_lib)
    if from_lib:
        print(f"  library: {len(from_lib)} owned clip(s) fit this beat")
    qs = queries_for(scene, note)
    print(f"  queries: {qs[:6]}{'…' if len(qs) > 6 else ''}")

    # start deep enough in the result pages that we are not re-offering page 1
    start_page = 1 + max(1, len(scene.get("clips", [])) // 8)
    picks, tried = [], set()
    WEB_TARGET = max(0, need_web)
    # collect per source first, then round-robin so one library cannot fill the
    # whole batch — variety of look matters as much as count
    buckets = {}
    for page in range(start_page, start_page + 4):
        for q in qs:
            for src in SOURCES:
                name = src.__name__.replace("search_", "")
                if len(buckets.get(name, [])) >= WEB_TARGET:
                    continue
                for c in src(q, page):
                    key = f"{c['source']}:{c['src_id']}"
                    purl = (c.get("page_url") or "").rstrip("/")
                    if key in tried or key in seen or (purl and purl in seen):
                        continue
                    tried.add(key)
                    desc = (c.get("title") or "").strip()
                    if blocked(f"{desc} {c.get('query','')}", profile):
                        continue
                    # A tagged candidate must EARN its place: its own words have to
                    # show a person, their hands or their work. Untagged ones (pexels
                    # often has no alt text) fall back to query relevance.
                    if desc and not has_signal(desc):
                        continue
                    if c.get("duration") and c["duration"] > 180:
                        continue
                    buckets.setdefault(name, []).append(c)
            if sum(len(v) for v in buckets.values()) >= WEB_TARGET * 2:
                break
        if sum(len(v) for v in buckets.values()) >= WEB_TARGET * 2:
            break
    order = [n for n in ("pexels", "pixabay", "coverr", "wikimedia") if buckets.get(n)]
    while order and len(picks) < WEB_TARGET:
        for name in list(order):
            if not buckets[name]:
                order.remove(name); continue
            picks.append(buckets[name].pop(0))
            if len(picks) >= WEB_TARGET:
                break

    if not picks and not from_lib:
        print("  ! nothing new found")
        return 0

    prev_dir = ROOT / "projects" / slug / "previews" / scene_id
    th_dir = ROOT / "projects" / slug / "thumbs" / scene_id
    prev_dir.mkdir(parents=True, exist_ok=True)
    th_dir.mkdir(parents=True, exist_ok=True)

    idx = next_index(scene, "V")
    added, credits = 0, []

    # library hits cost nothing: the preview and thumb are already committed here,
    # so we just point a new card entry at the files we already own.
    for a in from_lib:
        stem = f"{slug}-{scene_id}-V{idx:02d}"
        scene.setdefault("clips", []).append({
            "id": stem, "type": "video", "source": a["source"],
            "author": a.get("author", ""), "license": a.get("license", ""),
            "page_url": a.get("page_url", ""),
            "thumb": a.get("thumb", ""), "preview": a.get("preview", ""),
            "score": 0, "categories": a.get("subjects", []),
            "title": a.get("title", ""), "query": a.get("query", ""),
            "src_id": a.get("src_id", ""), "download_url": a.get("download_url", ""),
            "fresh": True, "added_by": "library",
        })
        credits.append(credit_line({**a, "license": a.get("license", "")}))
        idx += 1
        added += 1
    with tempfile.TemporaryDirectory() as td:
        for c in picks:
            stem = f"{slug}-{scene_id}-V{idx:02d}"
            master = pathlib.Path(td) / f"{stem}.mp4"
            try:
                with requests.get(c["download_url"], stream=True, timeout=90,
                                  headers={"User-Agent": UA}) as r:
                    r.raise_for_status()
                    with open(master, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
            except Exception as e:
                print(f"    download failed ({c['source']}): {str(e)[:80]}")
                continue
            if master.stat().st_size < 100_000:
                continue
            pv, th = prev_dir / f"{stem}.mp4", th_dir / f"{stem}.jpg"
            if not make_preview(master, pv, th):
                pv.unlink(missing_ok=True)
                continue
            scene.setdefault("clips", []).append({
                "id": stem, "type": "video", "source": c["source"],
                "author": c.get("author", ""), "license": c["license"],
                "page_url": c.get("page_url", ""),
                "thumb": str(th.relative_to(ROOT)), "preview": str(pv.relative_to(ROOT)),
                "score": 0, "categories": [], "title": c.get("title", ""),
                "query": c.get("query", ""),
                # re-download the full-res master at render time:
                "src_id": c.get("src_id", ""), "download_url": c.get("download_url", ""),
                "fresh": True, "added_by": "search-10-more",
            })
            credits.append(credit_line(c))
            idx += 1
            added += 1

    if added:
        json.dump(card, open(card_path, "w"), indent=1)
        cf = ROOT / "projects" / slug / "CREDITS.md"
        if not cf.exists():
            cf.write_text(f"# Credits — {slug}\n\n| source | title | author | license | page |\n|---|---|---|---|---|\n")
        with open(cf, "a") as fh:
            fh.write("\n".join(credits) + "\n")
    print(f"  + {added} new videos for {slug} {scene_id}")
    return added


def main():
    sel_dir = ROOT / "selections"
    pending = []
    for p in sorted(sel_dir.glob("*.json")):
        try:
            sel = json.load(open(p))
        except Exception:
            continue
        slug = sel.get("project") or p.stem
        for sid, req in (sel.get("topup_requests") or {}).items():
            if isinstance(req, dict) and not req.get("done"):
                pending.append((p, slug, sid, req.get("note", "")))

    if not pending:
        print("no pending top-up requests")
        return 0
    print(f"pending top-ups: {[(s, i) for _, s, i, _ in pending]}")

    total = 0
    for path, slug, sid, note in pending[:MAX_SCENES_PER_RUN]:
        profile = "belong" if slug.startswith("belong") else "edenrise"
        print(f"→ {slug} {sid}  ({note!r})")
        # materialise this project in the sparse checkout
        sh("git", "sparse-checkout", "add", f"projects/{slug}", cwd=ROOT)
        n = run_scene(slug, sid, note, profile)
        if n:
            sel = json.load(open(path))
            sel["topup_requests"][sid]["done"] = True
            sel["topup_requests"][sid]["fulfilled"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            sel["topup_requests"][sid]["added"] = n
            json.dump(sel, open(path, "w"), indent=2)
        total += n

    left = len(pending) - min(len(pending), MAX_SCENES_PER_RUN)
    if left:
        print(f"note: {left} more request(s) left for the next run (cap {MAX_SCENES_PER_RUN})")
    print(f"TOTAL_ADDED={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
