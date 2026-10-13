#!/usr/bin/env python3
"""Prove one failing beat cannot destroy a whole gather run.

On 2026-10-13 a run worked for 11.9 minutes across the queued beats, hit an exception on
one of them, and died. Because the workflow only commits when something is reported added,
the commit step was skipped and EVERY scene staged before the crash was lost — previews,
thumbs and strips already uploaded to Releases, orphaned with nothing pointing at them.
The same shape as the rebase bug: real work discarded by an all-or-nothing step.

This asserts the isolation:
  * a scene that raises is caught, recorded, and the run carries on to the next one;
  * the failure is written onto its own top-up request, so it can be read from git
    without admin rights on the Actions log;
  * scenes that succeeded still count toward TOTAL_ADDED, so their work is committed;
  * a request that failed stays open (done is not set) and gets an attempt count.

    python3 tools/verify/scene_isolation_harness.py
"""
import json, pathlib, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


src = (ROOT / "tools" / "topup_bot.py").read_text()

# --- the guard is actually in the loop, not just imported -----------------------------
loop = src[src.index("for path, slug, sid, note, reason, auto_avoid in pending"):
           src.index("print(f\"TOTAL_ADDED=")]
check("try:" in loop, "the per-scene loop has no try/except — one bad beat kills the run")
check("except Exception" in loop, "the loop does not catch scene failures")
check("continue" in loop, "a failed scene does not let the run carry on")
check('r["error"]' in loop, "a failure is not recorded onto its request")
check('r["attempts"]' in loop, "failures are not counted per request")
check('req.pop("error", None)' in loop, "a later success does not clear the old error")

# --- and the all-failed case still reaches git ----------------------------------------
tail = src[src.index("print(f\"TOTAL_ADDED="):]
check("push_cards.py" in tail,
      "when every scene fails nothing is committed, so the error stays invisible")
check("::warning::" in tail, "failures are not surfaced in the Actions summary")

# --- behaviour: simulate the loop's contract on a fake selections file ----------------
tmp = pathlib.Path(tempfile.mkdtemp(prefix="scene-isolation-"))
sel_p = tmp / "demo.json"
json.dump({"project": "demo", "approved": {"S01": ["keep_me"]},
           "topup_requests": {"S01": {"done": False}, "S02": {"done": False},
                              "S03": {"done": False}}},
          open(sel_p, "w"), indent=2)

import time


def run_loop(scenes):
    """The same shape as topup_bot's loop: isolate, record, carry on."""
    total, failures = 0, []
    for sid, outcome in scenes:
        try:
            if isinstance(outcome, Exception):
                raise outcome
            n = outcome
        except Exception as e:
            sel = json.load(open(sel_p))
            r = sel.setdefault("topup_requests", {}).setdefault(sid, {})
            r["error"] = f"{type(e).__name__}: {e}"
            r["attempts"] = int(r.get("attempts", 0)) + 1
            r["last_attempt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            json.dump(sel, open(sel_p, "w"), indent=2)
            failures.append(sid)
            continue
        if n:
            sel = json.load(open(sel_p))
            req = sel["topup_requests"][sid]
            req.update({"done": True, "added": n})
            req.pop("error", None)
            json.dump(sel, open(sel_p, "w"), indent=2)
        total += n
    return total, failures


# S01 works, S02 blows up, S03 works — the run must deliver 2 of 3, not 0 of 3
total, failures = run_loop([("S01", 14), ("S02", RuntimeError("release upload 422")),
                            ("S03", 11)])
sel = json.load(open(sel_p))
print(f"staged {total} clips across 2 scenes; {len(failures)} scene(s) failed")

check(total == 25, f"work from the healthy scenes was lost (TOTAL_ADDED={total}, want 25)")
check(failures == ["S02"], f"wrong scene recorded as failed: {failures}")
check(sel["topup_requests"]["S01"].get("done") is True, "S01's success was not recorded")
check(sel["topup_requests"]["S03"].get("done") is True,
      "S03 never ran — the run stopped at the failure instead of carrying on")
check(sel["topup_requests"]["S02"].get("done") is not True,
      "the failed request was wrongly marked fulfilled")
check("release upload 422" in sel["topup_requests"]["S02"].get("error", ""),
      "the failure reason is not readable from the request")
check(sel["topup_requests"]["S02"].get("attempts") == 1, "the attempt was not counted")
check(sel["approved"] == {"S01": ["keep_me"]}, "approvals were touched by the failure path")

# a retry that succeeds must clear the stale error
run_loop([("S02", 9)])
sel = json.load(open(sel_p))
check("error" not in sel["topup_requests"]["S02"],
      "a successful retry left the old error behind, so it would read as still broken")
print("a successful retry cleared the recorded error")

print()
for f in fails:
    print("FAIL:", f)
print(f"{'PASS' if not fails else 'FAILED'} — {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
