#!/usr/bin/env python3
"""A tick must never be lost, and must never move.

Re-gathers used to renumber clip ids, so approvals made before a renumber point at ids
that are no longer on the card — the client sees footage they approved simply gone.
This restores that footage TO THE SCENE IT WAS APPROVED ON, keeping the approved id, by
finding the same media (source + source id, or page_url) anywhere we still hold it:
the other cards, the shared library, or this card's own git history.

An approval is never moved to another scene and never deleted. What cannot be found is
reported for a human.

    python3 tools/recover_approvals.py --dry
    python3 tools/recover_approvals.py
"""
import json, re, subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRY = "--dry" in sys.argv
SKIP_CARDS = {"belong-module7"}                      # work in progress, off-limits
LEGACY = re.compile(r"^(pexels|pixabay|coverr|wikimedia|archive|unsplash|openverse)_([A-Za-z0-9]+)_")


def keys(clip):
    """Every identifier that survives a renumber."""
    out = set()
    src, sid = clip.get("source"), str(clip.get("src_id") or "")
    if src and sid:
        out.add(f"{src}:{sid}")
    u = (clip.get("page_url") or "").rstrip("/")
    if u:
        out.add(u)
    return out


def key_from_id(cid):
    m = LEGACY.match(cid)
    return f"{m.group(1)}:{m.group(2)}" if m else None


def build_index():
    """source:id and page_url -> a clip record we can still serve (has http media)."""
    idx = {}

    def add(rec):
        if not str(rec.get("preview", "")).startswith("http"):
            return
        for k in keys(rec):
            idx.setdefault(k, rec)

    for p in (ROOT / "projects").glob("*/scenes.json"):
        for s in json.load(open(p))["scenes"]:
            for c in s["clips"]:
                add(c)
    lib = ROOT / "library" / "index.json"
    if lib.exists():
        for a in json.load(open(lib)).get("assets", []):
            if not a.get("dead"):
                add(a)
    return idx


def history_records(slug, wanted_ids):
    """Walk this card's history for the revisions that still had these clips."""
    found = {}
    path = f"projects/{slug}/scenes.json"
    revs = subprocess.run(["git", "log", "--format=%H", "-60", "--", path],
                          capture_output=True, text=True).stdout.split()
    for rev in revs:
        if len(found) == len(wanted_ids):
            break
        out = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
        if out.returncode or not out.stdout.strip():
            continue
        try:
            card = json.loads(out.stdout)
        except Exception:
            continue
        for s in card["scenes"]:
            for c in s["clips"]:
                if c["id"] in wanted_ids and c["id"] not in found:
                    found[c["id"]] = (s["id"], c)
    return found


def main():
    idx = build_index()
    restored = unmatched = 0
    lines = []
    for sel_p in sorted((ROOT / "selections").glob("*.json")):
        slug = sel_p.stem
        if slug in SKIP_CARDS:
            continue
        card_p = ROOT / "projects" / slug / "scenes.json"
        if not card_p.exists():
            n = sum(len(v) for v in (json.load(open(sel_p)).get("approved") or {}).values())
            if n:
                lines.append(f"{slug}: no card in the cockpit — {n} approval(s) left untouched")
            continue
        sel = json.load(open(sel_p))
        card = json.load(open(card_p))
        scenes = {s["id"]: s for s in card["scenes"]}
        dangling = [(sid, cid) for sid, ids in (sel.get("approved") or {}).items()
                    for cid in ids if sid not in scenes or cid not in {c["id"] for c in scenes[sid]["clips"]}]
        if not dangling:
            continue
        hist = history_records(slug, {cid for _, cid in dangling})
        changed = False
        for sid, cid in dangling:
            if sid not in scenes:
                lines.append(f"{slug}: scene {sid} no longer exists — {cid} left untouched"); unmatched += 1
                continue
            src = None
            k = key_from_id(cid)
            if k and k in idx:
                src = idx[k]
            if src is None and cid in hist:
                old = hist[cid][1]
                for kk in keys(old):
                    if kk in idx:
                        src = idx[kk]; break
                if src is None and str(old.get("preview", "")).startswith("http"):
                    src = old                      # its own Release media still stands
            if src is None:
                lines.append(f"{slug} {sid}: {cid} — media not found anywhere, approval kept"); unmatched += 1
                continue
            rec = {k: v for k, v in src.items() if k not in ("used_in", "harvested", "dead", "key")}
            rec["id"] = cid                        # keep the id the client approved
            rec["restored"] = True
            rec.pop("judged", None); rec.pop("shown", None); rec.pop("rank", None)
            scenes[sid]["clips"].append(rec)
            restored += 1; changed = True
            lines.append(f"{slug} {sid}: restored {cid} ({rec.get('source')})")
        if changed and not DRY:
            json.dump(card, open(card_p, "w"), indent=1, ensure_ascii=False)
    print("\n".join(lines) or "nothing dangling")
    print(f"\nrestored {restored} approved clip(s) to their own scene; {unmatched} still unmatched"
          + ("  (dry run)" if DRY else ""))


if __name__ == "__main__":
    main()
