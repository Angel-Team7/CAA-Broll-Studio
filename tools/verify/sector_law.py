#!/usr/bin/env python3
"""Prove the sector registry is sound before the pipeline depends on it.

A bad sector entry does not crash a gather — it quietly poisons a night of footage
(a word in both `never` and `positive`, a seed the sector's own law bars, a card
pointing at a sector that does not exist). This checks all of it and exits non-zero.

    python3 tools/verify/sector_law.py
"""
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sectors
import topup_bot as tb
import recall

fails, warns = [], []


def check(cond, msg):
    if not cond:
        fails.append(msg)


reg = sectors.all_sectors()
check(len(reg) >= 2, "the registry is empty")
check(sectors.FALLBACK in reg, f"the fallback sector '{sectors.FALLBACK}' is not defined")

for sid, cfg in reg.items():
    for field in ("name", "world", "never", "positive", "prefix", "tail"):
        check(field in cfg, f"{sid}: missing '{field}'")
    never, pos = sectors.never(sid), sectors.positive(sid)
    both = never & pos
    check(not both, f"{sid}: {sorted(both)} sit in BOTH never and positive — every clip "
                    f"naming them is admitted and then barred")
    check(len(pos) >= 10, f"{sid}: only {len(pos)} positive words — the gate will pass everything")
    check(bool(cfg.get("prefix")), f"{sid}: no query prefix, so a bare note has no world to land in")

    # A seed is the house phrasing for a standard beat. If the sector's own law bars its
    # own seed, the harvester will shop for footage it then throws away.
    for seed in cfg.get("seeds") or []:
        check(not tb.blocked(seed, sid), f"{sid}: own seed is barred by its never-list — {seed!r}")
        check(tb.has_signal(seed, sid), f"{sid}: own seed shows none of its positive vocabulary — {seed!r}")
        check(len(seed.split()) <= 9, f"{sid}: seed is too long for a stock query — {seed!r}")
        check("," not in seed, f"{sid}: seed has a comma (breaks Pixabay tag search) — {seed!r}")
    if not cfg.get("seeds"):
        warns.append(f"{sid}: no seeds — the harvester cannot stock it before its first lesson")

# every published card must resolve to a sector that exists
proj = json.load(open(ROOT / "projects.json"))
declared = {p["slug"]: p.get("sector") for p in proj["projects"]}
for card in sorted((ROOT / "projects").glob("*/scenes.json")):
    slug = card.parent.name
    d = declared.get(slug)
    check(d is None or d in reg, f"{slug}: declares sector '{d}', which is not in the registry")
    check(sectors.for_slug(slug) in reg, f"{slug}: resolves to a sector that does not exist")
    if slug in declared and declared[slug] is None:
        warns.append(f"{slug}: no sector declared in projects.json — falling back to "
                     f"'{sectors.legacy_for_slug(slug)}'")

# the shelf must be able to answer each sector, or the sector is not stocked yet
assets = []
lib = ROOT / "library" / "index.json"
if lib.exists():
    assets = [a for a in json.load(open(lib))["assets"]
              if a.get("type") == "video" and a.get("preview") and not a.get("dead")]
if assets:
    print(f"shelf: {len(assets)} usable video assets")
    for sid in reg:
        seeds = reg[sid].get("seeds") or []
        if not seeds:
            continue
        shots = [{"id": chr(65 + i), "text": t, "pexels": t} for i, t in enumerate(seeds[:6])]
        n = len(recall.library_picks(shots, sid, set(), set(), 24, []))
        line = f"{sid:15s} shelf answers {n:2d}/24 of its own standard beats"
        if n >= 6:
            print(line)
        else:
            warns.append(line.strip() + " — thin, the harvester needs to run for it")

print()
for w in warns:
    print("warn:", w)
for f in fails:
    print("FAIL:", f)
print(f"\n{len(reg)} sectors · {len(fails)} failures · {len(warns)} warnings")
sys.exit(1 if fails else 0)
