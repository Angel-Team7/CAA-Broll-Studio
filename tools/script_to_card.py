#!/usr/bin/env python3
"""Turn a lesson script (Drive doc text) into a cockpit card, without guessing.

Input: plain text of a script in the client's format — scenes headed
"SCENE n — TITLE" (or "[SCENE n]"), with the avatar narration, and optional
"B-ROLL:" and "ON SCREEN TEXT:" / "ON-SCREEN:" blocks. Output: the card's
scenes.json gets, per scene, script_line = the words to be spoken,
visual_direction = the client's B-ROLL note, onscreen, and windows ESTIMATED
from word count at 145 wpm, marked timing_source=estimated.

Never touches clips or approvals. Never invents a quote: if a scene has no
narration the line is left empty and the card shows NARRATION NOT RECORDED YET.

    python3 tools/script_to_card.py <slug> <script.txt> [--title "Card title"]

Plain-prose scripts (no SCENE headers — the "current script of the rendered
video" docs) are handled too: if the card is already timed to the recorded
narration (timing_source=narration on any scene) the card is authoritative and
nothing is written; otherwise paragraphs are grouped into ~PROSE_WORDS-word
scenes with estimated windows and no visual brief.
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
WPM = 145.0
PROSE_WORDS = 55  # target spoken words per estimated scene when the script has no SCENE headers

def parse(text):
    text = text.replace("\r", "")
    # the checkpoint / closing block is not a scene — cut it off before splitting
    text = re.split(r"\n\s*(?:🎥\s*)?CHECKPOINT\b", "\n" + text, maxsplit=1)[0]
    # split on scene headers of either style
    parts = re.split(r"\n\s*(?:🎥\s*)?(?:\[SCENE\s*(\d+)\]|SCENE\s+(\d+)\s*[—-])", "\n" + text)
    scenes = []
    # parts: [pre, n1a, n1b, body1, n2a, n2b, body2, ...]
    for i in range(1, len(parts), 3):
        n = int(parts[i] or parts[i + 1]); body = parts[i + 2]
        if re.match(r"\s*CHECKPOINT", body, re.I): continue
        title = body.split("\n", 1)[0].strip(" —-")
        nar, broll, ons, field = [], [], [], "nar"
        for line in body.split("\n")[1:]:
            s = line.strip()
            if not s: continue
            if re.match(r"HEYGEN AVATAR", s, re.I): field = "nar"; continue
            if re.match(r"B-?ROLL:?", s, re.I): field = "broll"; s = re.sub(r"^B-?ROLL:?\s*", "", s, flags=re.I)
            elif re.match(r"ON[- ]?SCREEN( TEXT)?:?", s, re.I): field = "ons"; s = re.sub(r"^ON[- ]?SCREEN( TEXT)?:?\s*", "", s, flags=re.I)
            elif re.match(r"(PRODUCTION SOURCE NOTE|NOTE)\b", s, re.I): field = "skip"
            elif re.match(r"^---+$|^⸻$", s): continue
            if not s: continue
            {"nar": nar, "broll": broll, "ons": ons}.get(field, []).append(s)
        scenes.append({"n": n, "title": title, "narration": " ".join(nar),
                       "broll": " ".join(broll), "onscreen": " ".join(ons)})
    return scenes

def parse_prose(text):
    """Group the narration paragraphs of a header-less script into scenes."""
    text = text.replace("\r", "")
    # drop the metadata block above the first dashed rule, if there is one
    m = re.search(r"\n\s*\\*-{5,}\s*\n", text)
    if m: text = text[m.end():]
    text = re.split(r"\n\s*(?:🎥\s*)?CHECKPOINT\b", "\n" + text, maxsplit=1)[0]
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    paras = [p for p in paras if p and not re.match(r"^(\\?[-=_]{3,}|NOTE\b|NOTA\b|\[Visual)", p, re.I)]
    scenes, buf, n = [], [], 0
    for p in paras:
        buf.append(p)
        if len(re.findall(r"[\w']+", " ".join(buf))) >= PROSE_WORDS:
            n += 1; scenes.append({"n": n, "title": "", "narration": " ".join(buf), "broll": "", "onscreen": ""}); buf = []
    if buf:
        if scenes and len(re.findall(r"[\w']+", " ".join(buf))) < PROSE_WORDS // 2:
            scenes[-1]["narration"] += " " + " ".join(buf)
        else:
            n += 1; scenes.append({"n": n, "title": "", "narration": " ".join(buf), "broll": "", "onscreen": ""})
    return scenes

def card_is_audio_timed(slug):
    """A card is authoritative over a plain-prose doc when it is timed to the
    recorded narration, or when it is a legacy card that already carries lines
    for most of its scenes (built from the real narration before timing_source
    existed). Only empty or mostly-empty cards get rebuilt from prose."""
    card_p = ROOT / "projects" / slug / "scenes.json"
    if not card_p.exists(): return False
    sc = json.load(open(card_p))["scenes"]
    if any(s.get("timing_source") == "narration" for s in sc): return True
    with_lines = sum(1 for s in sc if (s.get("script_line") or "").strip())
    return bool(sc) and with_lines * 2 >= len(sc)

def apply(slug, scenes, title=None):
    card_p = ROOT / "projects" / slug / "scenes.json"
    card = json.load(open(card_p)) if card_p.exists() else {"scenes": []}
    by = {s["id"]: s for s in card["scenes"]}
    t = 0.0
    for sc in scenes:
        sid = f"S{sc['n']:02d}"
        tgt = by.get(sid)
        if tgt is None:
            tgt = {"id": sid, "clips": [], "quota": {"video": 7, "image": 3}}
            card["scenes"].append(tgt); by[sid] = tgt
        words = len(re.findall(r"[\w']+", sc["narration"]))
        dur = max(6.0, words / WPM * 60.0) if words else 20.0
        tgt["script_line"] = sc["narration"][:600]
        if sc["broll"]: tgt["visual_direction"] = sc["broll"]
        if sc["onscreen"]: tgt["onscreen"] = sc["onscreen"]
        tgt["t"] = round(t, 2); tgt["end"] = round(t + dur, 2)
        tgt["timing_source"] = "estimated" if words else "unrecorded"
        t += dur
    card["scenes"].sort(key=lambda s: float(s.get("t", 0)))
    card_p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(card, open(card_p, "w"), indent=1, ensure_ascii=False)
    reg_p = ROOT / "projects.json"; reg = json.load(open(reg_p))
    if not any(p["slug"] == slug for p in reg["projects"]):
        reg["projects"].append({"slug": slug, "title": title or slug,
                                "scenes": len(card["scenes"]),
                                "clips": sum(len(s["clips"]) for s in card["scenes"])})
        reg["projects"].sort(key=lambda p: p["slug"])
        json.dump(reg, open(reg_p, "w"), indent=1, ensure_ascii=False)
    return card, t

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(__doc__)
    slug, path = sys.argv[1], sys.argv[2]
    title = sys.argv[sys.argv.index("--title") + 1] if "--title" in sys.argv else None
    text = open(path, encoding="utf-8").read()
    scenes = parse(text)
    if not scenes:
        if card_is_audio_timed(slug):
            print(f"{slug}: plain-prose script, card already carries the narration — card is authoritative, nothing written")
            sys.exit(0)
        scenes = parse_prose(text)
        if not scenes: sys.exit("no narration found in the script")
        print(f"{slug}: no SCENE headers — {len(scenes)} scenes estimated from paragraphs (no visual brief in the script)")
    card, total = apply(slug, scenes, title)
    for s in scenes: print(f"  S{s['n']:02d} {len(s['narration'].split()):3}w  {s['narration'][:56]}…")
    print(f"applied {len(scenes)} scenes to {slug}; est. {total/60:.1f} min")
