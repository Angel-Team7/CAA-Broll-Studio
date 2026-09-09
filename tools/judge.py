#!/usr/bin/env python3
"""The judge's hands. Claude does the looking (see .claude/skills/judge/SKILL.md);
this tool finds the work, fetches the frames, and applies the verdicts.

    python3 tools/judge.py pending                       # scenes with unjudged clips
    python3 tools/judge.py strips <slug> <scene>         # download frames, print context
    python3 tools/judge.py apply <slug> <scene> <verdicts.json>
"""
import json, re, sys, time, pathlib, tempfile, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP = {"belong-module7"}
SHOW_TOP = 10          # clips shown on the card after judging
USABLE_AT = 6          # relevance floor for "usable"
GAP_BELOW = 3          # fewer usable than this → stock_gap
MAX_PER_SHOOT = 2


def proxy(url):
    reg = json.load(open(ROOT / "projects.json"))
    base = "https://github.com/Angel-Team7/CAA-Broll-Studio/releases/download/"
    mp = (reg.get("media_proxy") or "").rstrip("/")
    return (mp + "/" + url[len(base):]) if mp and url.startswith(base) else url


def pending():
    out = []
    for p in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = p.parent.name
        if slug in SKIP:
            continue
        for s in json.load(open(p))["scenes"]:
            n = sum(1 for c in s.get("clips", []) if c.get("judged") is False)
            if n:
                out.append((slug, s["id"], n))
                print(f"{slug} {s['id']} {n}")
    if not out:
        print("nothing pending")
    return out


def brand_rules(brand):
    txt = (ROOT / "CLAUDE.md").read_text()
    m = re.search(r"### (Edenrise|Belong).*?(?=\n### |\n## )", txt, re.S)
    for sec in re.findall(r"(### (?:Edenrise|Belong)[^\n]*\n(?:.*?\n)*?)(?=### |## )", txt):
        if brand == "belong" and sec.startswith("### Belong"):
            return sec
        if brand == "edenrise" and sec.startswith("### Edenrise"):
            return sec
    return ""


def strips(slug, sid):
    card = json.load(open(ROOT / "projects" / slug / "scenes.json"))
    sc = next(s for s in card["scenes"] if s["id"] == sid)
    brand = "belong" if slug.startswith("belong") else "edenrise"
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"judge-{slug}-{sid}-"))
    print(f"# {slug} {sid} — brand {brand}")
    print("HEARS:", (sc.get("script_line") or "(narration not recorded)").strip())
    print("BRIEF:", (sc.get("visual_direction") or "").strip())
    print("SHOTS:")
    for sh in sc.get("shots") or []:
        print(f"  {sh['id']} [{sh['scale']}] {sh['text']}")
    print("MUST NOT:", ", ".join(sc.get("must_not") or []) or "(none beyond the brand list)")
    print("BRAND RULES:\n" + brand_rules(brand))
    print("\nCLIPS (clip_id  path  source  title  duration):")
    for c in sc.get("clips", []):
        if c.get("judged") is not False:
            continue
        url = c.get("strip") or c.get("thumb") or ""
        kind = "strip" if c.get("strip") else "thumb-only"
        path = ""
        if url:
            ext = ".jpg" if not url.lower().endswith(".png") else ".png"
            path = tmp / (c["id"] + ext)
            try:
                urllib.request.urlretrieve(proxy(url), path)
            except Exception as e:
                path = f"(download failed: {e})"
        print(f"  {c['id']}  {path}  {c.get('source','')}  {(c.get('title') or c.get('query') or '')[:70]!r}  {c.get('duration','')}s  [{kind}]")
    print(f"\nframes in {tmp}")


def apply(slug, sid, vpath):
    p = ROOT / "projects" / slug / "scenes.json"
    card = json.load(open(p))
    sc = next(s for s in card["scenes"] if s["id"] == sid)
    verdicts = json.load(open(vpath))
    sel_p = ROOT / "selections" / f"{slug}.json"
    approved = set()
    if sel_p.exists():
        approved = set(json.load(open(sel_p)).get("approved", {}).get(sid, []))
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log = open(ROOT / "library" / "verdicts.jsonl", "a")
    rej_p = ROOT / "library" / "rejected.json"
    rejected = json.load(open(rej_p)) if rej_p.exists() else {}
    n = 0
    for c in sc["clips"]:
        v = verdicts.get(c["id"])
        if not v:
            continue
        c["judged"] = True
        c["relevance"] = int(v.get("relevance", 0))
        c["brand_fit"] = int(v.get("brand_fit", 0))
        c["caption"] = str(v.get("caption", "")).strip()
        c["violation"] = str(v.get("violation", "")).strip()
        c["shot"] = str(v.get("shot", "")).strip()
        c["shoot"] = str(v.get("shoot", "")).strip()
        c["score"] = round(0.65 * c["relevance"] + 0.35 * c["brand_fit"], 2)
        c["judged_at"] = now
        log.write(json.dumps({"slug": slug, "scene": sid, "clip": c["id"], "source": c.get("source"),
                              "src_id": c.get("src_id"), "page_url": c.get("page_url"), **v, "at": now}) + "\n")
        if c["violation"]:
            key = f"{c.get('source')}:{c.get('src_id') or c.get('page_url')}"
            rejected[key] = {"brand": "belong" if slug.startswith("belong") else "edenrise",
                             "reason": c["violation"], "at": now, "from": f"{slug}/{sid}"}
        n += 1
    log.close()
    json.dump(rejected, open(rej_p, "w"), indent=1, ensure_ascii=False)

    # rank every judged clip; approved clips are always shown; cap per shoot
    judged = [c for c in sc["clips"] if c.get("judged") is True]
    judged.sort(key=lambda c: (-(c.get("score") or 0), c["id"]))
    shown, per_shoot = 0, {}
    for rank, c in enumerate(judged, 1):
        c["rank"] = rank
        key = c.get("shoot") or c["id"]
        ok = shown < SHOW_TOP and per_shoot.get(key, 0) < MAX_PER_SHOOT and not c.get("violation")
        c["shown"] = bool(ok or c["id"] in approved)
        if ok:
            shown += 1
            per_shoot[key] = per_shoot.get(key, 0) + 1
    usable = sum(1 for c in judged if c.get("relevance", 0) >= USABLE_AT and not c.get("violation"))
    if usable < GAP_BELOW:
        sc["stock_gap"] = {"usable": usable, "at": now,
                           "reason": f"only {usable} clip(s) reached relevance {USABLE_AT} without a violation"}
    else:
        sc.pop("stock_gap", None)
    sc["judged_at"] = now
    json.dump(card, open(p, "w"), indent=1, ensure_ascii=False)
    print(f"{slug} {sid}: {n} verdict(s) applied, {shown} shown, {usable} usable" + (" — STOCK GAP" if usable < GAP_BELOW else ""))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "pending":
        pending()
    elif a[0] == "strips":
        strips(a[1], a[2])
    elif a[0] == "apply":
        apply(a[1], a[2], a[3])
    else:
        sys.exit(__doc__)
