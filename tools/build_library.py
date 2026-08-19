#!/usr/bin/env python3
"""Build the shared B-roll library index from everything ever published.

Every clip on every cockpit card already has a 480p preview and a thumb committed
to this repo. That IS the stock library — it just was not searchable. This walks
all projects/*/scenes.json and writes library/index.json: one row per unique clip,
carrying the facets a B-roll director actually files by.

Facet schema (controlled vocabulary where it matters, free tags otherwise):
  key          source:src_id — the identity of the footage, not of its use
  subjects     who is on screen        (worker, gardener, chef, team, hands…)
  actions      what they are doing     (building, planting, cooking, teaching…)
  setting      where                   (site, workshop, field, kitchen, indoor…)
  people       none | one | two | group
  scale        detail | close | medium | wide     (best-effort from words)
  brand        edenrise | belong        (which client's world it came from)
  tags         everything else, normalised
  used_in      [{project, scene}] — so we can see what has already been spent where
"""
import json, pathlib, re, sys, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent

VOCAB = {
    "subjects": {
        "worker": ("worker", "workers", "labourer", "laborer", "workman"),
        "builder": ("builder", "builders", "construction", "constructor", "bricklayer"),
        "carpenter": ("carpenter", "carpentry", "woodworker", "joiner"),
        "mason": ("mason", "masonry", "bricklayer", "plasterer"),
        "gardener": ("gardener", "gardening", "landscaper", "horticulturist"),
        "farmer": ("farmer", "farming", "grower", "harvester"),
        "chef": ("chef", "cook", "baker", "kitchen"),
        "host": ("waiter", "waitress", "server", "receptionist", "host", "hospitality"),
        "engineer": ("engineer", "architect", "surveyor", "foreman", "supervisor"),
        "team": ("team", "crew", "colleagues", "coworkers", "group", "together"),
        "hands": ("hand", "hands", "fingers", "palm"),
        "woman": ("woman", "female", "she"),
        "man": ("man", "male", "he"),
    },
    "actions": {
        "building": ("build", "building", "construct", "constructing", "assemble", "framing"),
        "repairing": ("repair", "repairing", "fixing", "maintenance", "renovation", "restoring"),
        "planting": ("plant", "planting", "sowing", "seeding", "potting", "transplant"),
        "harvesting": ("harvest", "harvesting", "picking", "gathering", "reaping"),
        "pruning": ("prune", "pruning", "trimming", "cutting", "clipping"),
        "watering": ("water", "watering", "irrigation", "hose"),
        "cooking": ("cook", "cooking", "baking", "kneading", "chopping", "frying"),
        "serving": ("serve", "serving", "plating", "pouring", "hosting"),
        "measuring": ("measure", "measuring", "level", "align", "marking", "ruler"),
        "lifting": ("lift", "lifting", "carrying", "hauling", "loading"),
        "cleaning": ("clean", "cleaning", "sweeping", "tidying", "washing"),
        "teaching": ("teach", "teaching", "training", "showing", "instructing", "mentor"),
        "talking": ("talk", "talking", "conversation", "discussing", "meeting", "listening"),
        "planning": ("plan", "planning", "blueprint", "drawing", "sketching", "notes", "writing"),
        "inspecting": ("inspect", "inspecting", "checking", "examining", "reviewing"),
        "welding": ("weld", "welding", "grinding", "soldering"),
        "painting": ("paint", "painting", "plastering", "coating"),
    },
    "setting": {
        "site": ("site", "construction site", "scaffolding", "worksite"),
        "workshop": ("workshop", "shop", "garage", "studio", "bench"),
        "field": ("field", "farm", "orchard", "vineyard", "grove", "meadow", "soil", "land"),
        "garden": ("garden", "greenhouse", "nursery", "allotment"),
        "kitchen": ("kitchen", "restaurant", "bakery", "canteen"),
        "hotel": ("hotel", "resort", "guesthouse", "lodge", "farmhouse"),
        "outdoor": ("outdoor", "outside", "outdoors", "open air"),
        "indoor": ("indoor", "inside", "interior", "room"),
    },
}
SCALE = {
    "detail": ("closeup", "close up", "close-up", "macro", "detail"),
    "wide": ("aerial", "drone", "wide", "landscape", "panorama", "establishing"),
}
PEOPLE = {
    "two": ("two", "pair", "couple", "both", "each other"),
    "group": ("team", "crew", "group", "colleagues", "people", "workers", "together"),
    "one": ("man", "woman", "person", "worker", "someone", "portrait"),
}

def toks(*parts):
    t = set()
    for p in parts:
        for w in re.findall(r"[a-z]+", str(p or "").lower()):
            t.add(w)
            if len(w) > 3 and w.endswith("s"):
                t.add(w[:-1])
    return t

def facet(t, table):
    out = []
    for label, words in table.items():
        if any((" " in w and w in " ".join(sorted(t))) or w in t for w in words):
            out.append(label)
    return out

def classify(clip, brand):
    text = " ".join(str(clip.get(k) or "") for k in ("title", "query", "id"))
    cats = " ".join(clip.get("categories") or [])
    t = toks(text, cats)
    scale = next((k for k, ws in SCALE.items() if any(w in text.lower() for w in ws)), "medium")
    people = next((k for k, ws in PEOPLE.items() if t & set(ws)), "none")
    return {
        "subjects": facet(t, VOCAB["subjects"]),
        "actions": facet(t, VOCAB["actions"]),
        "setting": facet(t, VOCAB["setting"]),
        "scale": scale, "people": people, "brand": brand,
        "tags": sorted(w for w in t if len(w) > 3)[:24],
    }

def main():
    rows = {}
    for card in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = card.parent.name
        brand = "belong" if slug.startswith("belong") else "edenrise"
        try:
            data = json.load(open(card))
        except Exception as e:
            print(f"  ! {slug}: {e}"); continue
        for sc in data.get("scenes", []):
            for c in sc.get("clips", []):
                if c.get("source") == "upload":
                    continue                      # client's own files: not reusable stock
                key = f"{c.get('source')}:{c.get('src_id') or c.get('page_url') or c['id']}"
                r = rows.get(key)
                if not r:
                    r = rows[key] = {
                        "key": key, "source": c.get("source", ""),
                        "src_id": c.get("src_id", ""), "page_url": c.get("page_url", ""),
                        "type": c.get("type", "video"),
                        "title": c.get("title", ""), "query": c.get("query", ""),
                        "author": c.get("author", ""), "license": c.get("license", ""),
                        "download_url": c.get("download_url", ""),
                        "preview": c.get("preview", ""), "thumb": c.get("thumb", ""),
                        "used_in": [],
                    }
                    r.update(classify(c, brand))
                r["used_in"].append({"project": slug, "scene": sc["id"], "clip_id": c["id"]})

    lib = {"generated": "build_library.py", "count": len(rows),
           "assets": sorted(rows.values(), key=lambda r: r["key"])}
    out = ROOT / "library"; out.mkdir(exist_ok=True)
    json.dump(lib, open(out / "index.json", "w"), separators=(",", ":"))

    vids = sum(1 for r in rows.values() if r["type"] == "video")
    reuse = sum(1 for r in rows.values() if len(r["used_in"]) > 1)
    print(f"library: {len(rows)} unique assets ({vids} video, {len(rows)-vids} image)")
    print(f"  already reused across scenes: {reuse}")
    for f in ("subjects", "actions", "setting"):
        c = collections.Counter(x for r in rows.values() for x in r[f])
        print(f"  top {f}: {dict(c.most_common(8))}")
    print(f"  wrote {out/'index.json'} ({(out/'index.json').stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    sys.exit(main())
