#!/usr/bin/env python3
"""The sector registry — one place that says what world a card lives in.

The studio used to know two brands and nothing else: `slug.startswith("belong")` decided
the blocklist, the search flavour and the judge's rules, in eight different files. That
capped the studio at two clients. A sector is the same idea made open: a named world with
its own never-list, its own earn-your-place vocabulary and its own query flavour, declared
in `sectors.json` and resolved per project.

A project names its sector in `projects.json` (`"sector": "office"`). With none named, the
legacy rule still applies — `belong-*` → belong, anything else → edenrise — so every
existing card, every selection and all 5,000+ library assets keep working untouched.

    python3 tools/sectors.py                 # list every sector
    python3 tools/sectors.py <slug>          # which sector a card resolves to, and why
    python3 tools/sectors.py --check         # every card's sector, and any unknown names
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sectors.json"
FALLBACK = "universal"

# Junk that is never footage, whatever the sector.
JUNK_PHRASES = ("thanks for watching", "thank you for watching", "no copyright",
                "free download", "lower third", "green screen", "stock footage")

_cache = {}


def all_sectors():
    """id -> sector config, straight from the registry."""
    if "reg" not in _cache:
        reg = json.load(open(REGISTRY))
        _cache["reg"] = {k: v for k, v in reg.items() if not k.startswith("_")}
    return _cache["reg"]


def get(sector):
    """One sector's config. An unknown name falls back to universal rather than crashing a
    gather — a typo in projects.json must not lose a night's footage."""
    reg = all_sectors()
    if sector in reg:
        return reg[sector]
    return reg.get(FALLBACK, {"name": sector, "world": "", "never": [], "positive": [],
                              "prefix": [], "tail": ""})


def _projects():
    if "proj" not in _cache:
        p = ROOT / "projects.json"
        try:
            data = json.load(open(p))
            items = data.get("projects", data) if isinstance(data, dict) else data
            _cache["proj"] = {x["slug"]: x for x in items if isinstance(x, dict) and x.get("slug")}
        except Exception:
            _cache["proj"] = {}
    return _cache["proj"]


def legacy_for_slug(slug):
    """The rule the studio ran on before sectors existed. Still the default so that no
    existing card changes behaviour the day sectors land."""
    return "belong" if str(slug).startswith("belong") else "edenrise"


def for_slug(slug):
    """The sector id for a card: what projects.json declares, else the legacy rule."""
    declared = (_projects().get(slug) or {}).get("sector")
    if declared and declared in all_sectors():
        return declared
    return legacy_for_slug(slug)


def never(sector):
    return {w.lower() for w in get(sector).get("never", [])}


def positive(sector):
    return {w.lower() for w in get(sector).get("positive", [])}


def prefixes(sector):
    return list(get(sector).get("prefix", [])) or ["person at work"]


def tail(sector):
    return get(sector).get("tail", "")


def world(sector):
    return get(sector).get("world", "")


def name(sector):
    return get(sector).get("name", sector)


def rules_text(sector):
    """The sector's standing law, as the judge should read it."""
    s = get(sector)
    lines = [f"SECTOR: {s.get('name', sector)}"]
    if s.get("world"):
        lines.append(f"WORLD: {s['world']}")
    if s.get("never"):
        lines.append("NEVER: " + ", ".join(s["never"]))
    return "\n".join(lines)


def main():
    args = [a for a in sys.argv[1:]]
    if "--check" in args:
        bad = []
        for p in sorted((ROOT / "projects").glob("*/scenes.json")):
            slug = p.parent.name
            declared = (_projects().get(slug) or {}).get("sector")
            sec = for_slug(slug)
            how = "declared" if declared and declared in all_sectors() else "legacy"
            if declared and declared not in all_sectors():
                how = f"UNKNOWN '{declared}' → legacy"
                bad.append(slug)
            print(f"{slug:42s} {sec:16s} ({how})")
        print(f"\n{len(bad)} card(s) name a sector that is not in the registry" if bad
              else "\nevery card resolves to a known sector")
        return
    if args:
        slug = args[0]
        sec = for_slug(slug)
        print(f"{slug} → {sec}")
        print(rules_text(sec))
        print("POSITIVE: " + ", ".join(sorted(positive(sec))[:40]) + " …")
        return
    for sid, s in all_sectors().items():
        print(f"{sid:16s} {s.get('name','')}")
        print(f"{'':16s} never {len(s.get('never',[]))} · positive {len(s.get('positive',[]))}")


if __name__ == "__main__":
    main()
