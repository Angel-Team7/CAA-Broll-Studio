#!/usr/bin/env python3
"""Commit and push bot output without ever losing it to a conflict.

The topup bot and the judge both write `projects/**/scenes.json`. The topup runs in a
GitHub Action, the judge in a Claude routine, so no concurrency group covers both: on
2026-09-23 a run staged 181 candidates — previews, thumbs and strips already uploaded to
Releases — and lost every one of them, because the push step did
`git rebase origin/main || git rebase --abort` and a content conflict in scenes.json
cannot rebase. Five attempts, five aborts, work gone with the runner.

Rebasing is the wrong tool. Everything these bots produce is an APPEND — candidates onto a
card, assets onto the shelf, lines onto a log — and an append can always be replayed onto
whatever the file says now. So this snapshots what the run produced, resets to origin,
replays the append, and pushes, rebuilding on the fresh origin after every rejection.
There is no conflict to resolve because nothing is ever rebased.

Rules it will not break:
  * `selections/*.json` — only the `topup_requests` keys this run changed are replayed.
    `approved` is taken from origin, untouched, always. A tick cannot be lost here.
  * an existing clip is never modified, reordered or removed, so the judge's verdicts on
    clips already on the card survive: only unknown clip ids are appended.
  * `library/index.json` rows origin already has stay as origin wrote them, including
    `dead` flags and `used_in` — findings we paid to learn, never overwritten from a
    stale in-memory copy.

    python3 tools/push_cards.py "[topup-bot] Search 10 more: +181 candidates"
    python3 tools/push_cards.py --dry "msg"
"""
import json, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRIES = 6

CARDS = "projects/"
SELECTIONS = "selections/"
LIB_INDEX = "library/index.json"
TEXT_APPEND = ("library/CREDITS.md", "library/harvest_log.jsonl", "library/verdicts.jsonl")
LIB_JSON = ("library/rejected.json", "library/exemplars.json", "library/drive_seen.json")


def sh(*args, check=True):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"! {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r


def changed_files():
    out = []
    for line in sh("git", "status", "--porcelain").stdout.splitlines():
        path = line[3:].strip().strip('"')
        if path.startswith(CARDS) and path.endswith("scenes.json"):
            out.append(path)
        elif path.startswith(SELECTIONS) and path.endswith(".json"):
            out.append(path)
        elif path == LIB_INDEX or path in TEXT_APPEND or path in LIB_JSON:
            out.append(path)
    return out


def snapshot(paths):
    """What this run produced, read before we go anywhere near origin."""
    mine = {}
    for p in paths:
        fp = ROOT / p
        if not fp.exists():
            continue
        if p in TEXT_APPEND:
            mine[p] = fp.read_text()
            continue
        try:
            mine[p] = json.load(open(fp))
        except Exception as e:
            print(f"  ! {p} is not readable JSON ({e}) — left for a human, not pushed")
    return mine


def replay_card(mine, fresh):
    """Append clips origin does not have. Never touch one it does."""
    fresh_scenes = {s["id"]: s for s in fresh.get("scenes", [])}
    added = 0
    for s in mine.get("scenes", []):
        tgt = fresh_scenes.get(s["id"])
        if tgt is None:
            fresh.setdefault("scenes", []).append(s)
            added += len(s.get("clips") or [])
            continue
        have = {c["id"] for c in tgt.setdefault("clips", [])}
        for c in s.get("clips") or []:
            if c["id"] not in have:
                tgt["clips"].append(c); have.add(c["id"]); added += 1
        for field in ("shots", "must_not", "shots_by", "shots_at"):
            if s.get(field) and not tgt.get(field):
                tgt[field] = s[field]          # a shot list authored on a beat with none
        for field in ("stock_gap", "stock_gap_reason"):
            if field in s and field not in tgt:
                tgt[field] = s[field]
    return added


def replay_selection(mine, fresh, touched):
    """Only the top-up bookkeeping this run changed. `approved` is origin's, always."""
    mreq = mine.get("topup_requests") or {}
    freq = fresh.setdefault("topup_requests", {})
    n = 0
    for sid in touched:
        if sid in mreq:
            freq[sid] = mreq[sid]; n += 1
    if mine.get("updated"):
        fresh["updated"] = mine["updated"]
    return n


def replay_library(mine, fresh):
    """Append assets origin has not got; leave the ones it has exactly as they are."""
    have = {a.get("key") for a in fresh.get("assets", [])}
    added = 0
    for a in mine.get("assets", []):
        if a.get("key") and a["key"] not in have:
            fresh.setdefault("assets", []).append(a); have.add(a["key"]); added += 1
    fresh["assets"].sort(key=lambda r: r.get("key", ""))
    fresh["count"] = len(fresh["assets"])
    return added


def replay_text(mine_text, base_text, fp):
    """Lines this run added to an append-only log, re-appended to origin's version."""
    base = set(base_text.splitlines())
    new = [l for l in mine_text.splitlines() if l and l not in base]
    if not new:
        return 0
    cur = fp.read_text() if fp.exists() else ""
    if cur and not cur.endswith("\n"):
        cur += "\n"
    fp.write_text(cur + "\n".join(new) + "\n")
    return len(new)


def main():
    dry = "--dry" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry"]
    if not args:
        sys.exit(__doc__)
    message = args[0]

    paths = changed_files()
    if not paths:
        print("nothing to push"); return 0
    mine = snapshot(paths)
    if not mine:
        print("nothing readable to push"); return 0

    # Which top-up requests did this run actually change? Compare against HEAD now, while
    # HEAD is still the commit the run started from.
    touched, base_text = {}, {}
    for p in mine:
        if p.startswith(SELECTIONS):
            raw = sh("git", "show", f"HEAD:{p}", check=False).stdout
            try:
                was = (json.loads(raw).get("topup_requests") or {}) if raw.strip() else {}
            except Exception:
                was = {}
            now = mine[p].get("topup_requests") or {}
            touched[p] = [sid for sid, r in now.items() if was.get(sid) != r]
        elif p in TEXT_APPEND:
            base_text[p] = sh("git", "show", f"HEAD:{p}", check=False).stdout

    print(f"replaying {len(mine)} file(s)")
    for attempt in range(1, TRIES + 1):
        sh("git", "fetch", "-q", "origin", "main")
        sh("git", "reset", "-q", "--hard", "origin/main")
        clips = reqs = lines = 0
        for p, doc in mine.items():
            fp = ROOT / p
            fp.parent.mkdir(parents=True, exist_ok=True)
            if p in TEXT_APPEND:
                lines += replay_text(doc, base_text.get(p, ""), fp)
            elif p == LIB_INDEX:
                if fp.exists():
                    fresh = json.load(open(fp))
                    clips += replay_library(doc, fresh)
                    json.dump(fresh, open(fp, "w"), separators=(",", ":"))
                else:
                    json.dump(doc, open(fp, "w"), separators=(",", ":"))
            elif p in LIB_JSON:
                json.dump(doc, open(fp, "w"), indent=1, ensure_ascii=False)
            elif p.startswith(CARDS):
                if fp.exists():
                    fresh = json.load(open(fp))
                    clips += replay_card(doc, fresh)
                    json.dump(fresh, open(fp, "w"), indent=1, ensure_ascii=False)
                else:
                    json.dump(doc, open(fp, "w"), indent=1, ensure_ascii=False)
                    clips += sum(len(s.get("clips") or []) for s in doc.get("scenes", []))
            else:
                fresh = json.load(open(fp)) if fp.exists() else {
                    "project": pathlib.Path(p).stem, "ready": False,
                    "approved": {}, "needs_broll": {}, "topup_requests": {}}
                reqs += replay_selection(doc, fresh, touched.get(p, []))
                json.dump(fresh, open(fp, "w"), indent=2, ensure_ascii=False)
        print(f"  attempt {attempt}: replayed {clips} clip(s)/asset(s), "
              f"{reqs} request(s), {lines} log line(s)")
        if dry:
            print("  (dry run — nothing committed)")
            return 0
        for d in ("projects", "selections", "library"):
            if (ROOT / d).exists():
                sh("git", "add", d)
        if not sh("git", "status", "--porcelain", check=False).stdout.strip():
            print("  origin already has all of it — nothing to push"); return 0
        sh("git", "commit", "-q", "-m", message)
        if sh("git", "push", "-q", "origin", "HEAD:main", check=False).returncode == 0:
            print(f"  pushed: {message}")
            return 0
        print(f"  push rejected — rebuilding on the new origin (attempt {attempt})")
        time.sleep(attempt * 4)
    print(f"::error::could not push after replaying onto origin {TRIES} times")
    return 1


if __name__ == "__main__":
    sys.exit(main())
