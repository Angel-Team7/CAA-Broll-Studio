#!/usr/bin/env python3
"""Shot lists on cards — the bridge between what the viewer hears and what stock
engines can find. See .claude/skills/shot-list/SKILL.md.

    python3 tools/shot_list.py show <slug>          # print every beat for authoring
    python3 tools/shot_list.py pending               # scenes with no shots, all cards
    python3 tools/shot_list.py apply <slug> <json>   # validate + write shots/must_not
"""
import json, re, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCALES = {"wide", "medium", "close"}
SKIP = {"belong-module7", "edenrise-builders-pool", "belong-craveiral-originals", "belong-module2-heygen"}


def brand_of(slug):
    return "belong" if slug.startswith("belong") else "edenrise"


def title_of(slug):
    reg = json.load(open(ROOT / "projects.json"))
    return next((p.get("title") for p in reg["projects"] if p["slug"] == slug), slug)


def load(slug):
    p = ROOT / "projects" / slug / "scenes.json"
    return p, json.load(open(p))


def show(slug):
    _, card = load(slug)
    print(f"# {slug} — {title_of(slug)} — brand: {brand_of(slug)}")
    for s in sorted(card["scenes"], key=lambda x: int(re.sub(r"\D", "", x["id"]) or 0)):
        print(f"\n## {s['id']}  ({s.get('timing_source', '?')}, {len(s.get('clips', []))} clips, shots: {len(s.get('shots', []))})")
        print("HEARS:", (s.get("script_line") or "(narration not recorded)").strip())
        print("BRIEF:", (s.get("visual_direction") or "").strip())
        if s.get("onscreen"):
            print("ON-SCREEN:", s["onscreen"].strip())


def pending():
    out = []
    for p in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = p.parent.name
        if slug in SKIP:
            continue
        card = json.load(open(p))
        missing = [s["id"] for s in card["scenes"] if not s.get("shots")]
        if missing:
            out.append((slug, missing))
            print(f"{slug}: {len(missing)} scene(s) without shots: {' '.join(missing)}")
    if not out:
        print("nothing pending")
    return out


def validate(sid, entry):
    shots = entry.get("shots") or []
    if not 3 <= len(shots) <= 6:
        raise ValueError(f"{sid}: need 3–6 shots, got {len(shots)}")
    ids = set()
    for sh in shots:
        for k in ("id", "text", "pexels", "pixabay", "scale"):
            if not str(sh.get(k, "")).strip():
                raise ValueError(f"{sid}: shot missing {k}: {sh}")
        if sh["scale"] not in SCALES:
            raise ValueError(f"{sid}: scale must be wide|medium|close, got {sh['scale']}")
        if len(sh["pexels"].split()) > 9:
            raise ValueError(f"{sid}: pexels phrasing too long: {sh['pexels']!r}")
        if "," in sh["pixabay"]:
            raise ValueError(f"{sid}: pixabay phrasing must be plain words, no commas")
        if sh["id"] in ids:
            raise ValueError(f"{sid}: duplicate shot id {sh['id']}")
        ids.add(sh["id"])
    scales = {sh["scale"] for sh in shots}
    if len(scales) < 2:
        raise ValueError(f"{sid}: vary the scale (only {scales})")
    mn = entry.get("must_not") or []
    if len(mn) > 8:
        raise ValueError(f"{sid}: must_not has {len(mn)} items (max 8)")
    return shots, mn


def apply(slug, path, by="claude"):
    p, card = load(slug)
    data = json.load(open(path))
    scenes = {s["id"]: s for s in card["scenes"]}
    n = 0
    for sid, entry in data.items():
        if sid not in scenes:
            raise SystemExit(f"{slug} has no scene {sid}")
        shots, mn = validate(sid, entry)
        sc = scenes[sid]
        sc["shots"] = shots
        sc["must_not"] = mn
        sc["shots_by"] = by
        sc["shots_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        n += 1
    json.dump(card, open(p, "w"), indent=1, ensure_ascii=False)
    print(f"{slug}: shot lists written for {n} scene(s)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "show":
        show(a[1])
    elif a[0] == "pending":
        pending()
    elif a[0] == "apply":
        apply(a[1], a[2], by=(a[3] if len(a) > 3 else "claude"))
    else:
        sys.exit(__doc__)
