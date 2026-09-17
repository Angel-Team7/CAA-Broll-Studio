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
  sector       a sector id from sectors.json (which world it came from; field name
               stays `brand` for the rows already on the shelf)
  tags         everything else, normalised
  used_in      [{project, scene}] — so we can see what has already been spent where
"""
import json, pathlib, re, sys, collections

import sectors

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
        # the sectors beyond land and hospitality: a shot list for an office, a ward or a
        # shop floor has to be able to match the shelf, or every new sector's beat goes
        # to the web from scratch every single time
        "nurse": ("nurse", "carer", "caregiver", "care worker", "midwife", "paramedic"),
        "doctor": ("doctor", "physician", "clinician", "surgeon", "dentist"),
        "patient": ("patient", "resident", "elderly", "client"),
        "teacher": ("teacher", "trainer", "tutor", "instructor", "lecturer", "mentor"),
        "student": ("student", "learner", "pupil", "apprentice", "trainee", "class"),
        "customer": ("customer", "shopper", "buyer", "guest", "visitor"),
        "assistant": ("assistant", "shopkeeper", "cashier", "clerk", "salesperson"),
        "driver": ("driver", "courier", "rider", "delivery"),
        "operator": ("operator", "machinist", "welder", "fabricator", "assembler"),
        "technician": ("technician", "mechanic", "electrician", "plumber", "installer", "fitter"),
        "adviser": ("adviser", "advisor", "consultant", "accountant", "banker", "agent"),
        "developer": ("developer", "programmer", "coder", "analyst", "designer"),
        "manager": ("manager", "leader", "director", "boss", "executive", "officer"),
        "cleaner": ("cleaner", "housekeeper", "janitor", "maid"),
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
        "talking": ("talk", "talking", "conversation", "discussing", "meeting", "listening",
                    "listen", "explain", "explaining", "asking", "answering"),
        "planning": ("plan", "planning", "blueprint", "drawing", "sketching", "notes", "writing"),
        "inspecting": ("inspect", "inspecting", "checking", "examining", "reviewing"),
        "welding": ("weld", "welding", "grinding", "soldering"),
        "painting": ("paint", "painting", "plastering", "coating"),
        "presenting": ("present", "presenting", "pitching", "whiteboard", "flipchart", "slides"),
        "typing": ("typing", "keyboard", "laptop", "computer", "desk work"),
        "coding": ("code", "coding", "programming", "debugging", "screen"),
        "calling": ("call", "calling", "phone", "headset", "helpdesk", "support"),
        "greeting": ("greet", "greeting", "welcoming", "handshake", "check-in", "reception"),
        "selling": ("sell", "selling", "till", "checkout", "payment", "card", "transaction"),
        "scanning": ("scan", "scanning", "barcode", "scanner", "label"),
        "packing": ("pack", "packing", "packaging", "boxing", "wrapping", "picking"),
        "driving": ("drive", "driving", "delivering", "van", "truck", "route"),
        "caring": ("care", "caring", "help", "helping", "assist", "assisting",
                   "supporting", "comforting", "guiding"),
        "treating": ("treat", "treating", "examining patient", "bandage", "consultation", "diagnosis"),
        "signing": ("sign", "signing", "signature", "paperwork", "form", "contract"),
        "counting": ("count", "counting", "stocktake", "inventory", "tally", "figures"),
        "stocking": ("stock", "stocking", "restocking", "shelf", "shelves", "display"),
        "operating": ("operate", "operating", "machine", "machinery", "controls", "panel", "lathe"),
        "installing": ("install", "installing", "wiring", "mounting", "fitting", "connecting"),
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
        "office": ("office", "desk", "workspace", "meeting room", "boardroom", "coworking"),
        "clinic": ("clinic", "hospital", "ward", "surgery", "care home", "pharmacy", "practice"),
        "shop": ("shop", "store", "supermarket", "boutique", "market", "retail", "counter"),
        "warehouse": ("warehouse", "depot", "logistics", "loading bay", "aisle", "racking"),
        "factory": ("factory", "plant", "production line", "assembly line", "industrial"),
        "classroom": ("classroom", "school", "college", "lecture", "training room"),
        "street": ("street", "road", "pavement", "town", "city", "doorstep"),
        "vehicle": ("van", "truck", "car", "cab", "lorry", "forklift"),
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
    # The judge's caption is the best description we have of a clip — a human-grade line
    # about what is actually on screen — so index it alongside the stock metadata.
    text = " ".join(str(clip.get(k) or "") for k in ("caption", "title", "query", "id"))
    cats = " ".join(clip.get("categories") or [])
    t = toks(text, cats)
    scale = next((k for k, ws in SCALE.items() if any(w in text.lower() for w in ws)), "medium")
    people = next((k for k, ws in PEOPLE.items() if t & set(ws)), "none")
    return {
        "subjects": facet(t, VOCAB["subjects"]),
        "actions": facet(t, VOCAB["actions"]),
        "setting": facet(t, VOCAB["setting"]),
        "scale": scale, "people": people, "brand": brand, "sector": brand,
        "tags": sorted(w for w in t if len(w) > 3)[:24],
    }

def main():
    rows = {}
    for card in sorted((ROOT / "projects").glob("*/scenes.json")):
        slug = card.parent.name
        brand = sectors.for_slug(slug)      # a sector id; `brand` is the stored field name
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

    # The shelf is NOT derivable from the cards. The harvester stocks it ahead of demand,
    # so thousands of rows have never been on a card, and `dead` flags are findings we
    # paid to learn. A rebuild MERGES: cards refresh facets and usage, everything else on
    # the shelf stays exactly where it is.
    out = ROOT / "library"; out.mkdir(exist_ok=True)
    idx_p = out / "index.json"
    kept = new = 0
    if idx_p.exists():
        existing = json.load(open(idx_p))["assets"]
        for a in existing:
            r = rows.get(a["key"])
            if r is None:
                rows[a["key"]] = a                  # harvested stock, no card uses it yet
                kept += 1
                continue
            for f in ("dead", "harvested", "theme", "author", "license", "download_url"):
                if a.get(f) and not r.get(f):
                    r[f] = a[f]                     # findings and provenance survive
            if a.get("dead"):
                r["dead"] = a["dead"]
        new = len(rows) - len(existing) if len(rows) > len(existing) else 0
    lib = {"generated": "build_library.py", "count": len(rows),
           "assets": sorted(rows.values(), key=lambda r: r["key"])}
    json.dump(lib, open(idx_p, "w"), separators=(",", ":"))
    if kept:
        print(f"  kept {kept} harvested asset(s) that no card uses yet")

    vids = sum(1 for r in rows.values() if r.get("type") == "video")
    reuse = sum(1 for r in rows.values() if len(r.get("used_in") or []) > 1)
    print(f"library: {len(rows)} unique assets ({vids} video, {len(rows)-vids} image)")
    print(f"  already reused across scenes: {reuse}")
    for f in ("subjects", "actions", "setting"):
        c = collections.Counter(x for r in rows.values() for x in (r.get(f) or []))
        print(f"  top {f}: {dict(c.most_common(8))}")
    print(f"  wrote {out/'index.json'} ({(out/'index.json').stat().st_size/1e6:.1f} MB)")

if __name__ == "__main__":
    sys.exit(main())
