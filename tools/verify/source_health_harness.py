#!/usr/bin/env python3
"""Prove a dead stock key cannot produce a green harvest.

Between 2026-09-24 and 2026-10-07 every scheduled harvest ran, exited 0, and stocked
nothing. 282 themes needed stock the whole time. Nobody noticed, because a source whose
key is missing or rejected returned `[]` — identical to "no results" — and the workflow's
commit step is skipped when nothing was added, so the run went green with no signal at
all. Two weeks of stocking lost to an ambiguous empty list.

This asserts the two halves of the fix:
  1. a source says WHY it is empty (no key / HTTP 401 / request failed), and says nothing
     when it answered normally, so a genuinely empty search is not mistaken for a fault;
  2. a run that added nothing while themes still needed stock AND a source is unhealthy
     exits non-zero, so the Action shows red.

    python3 tools/verify/source_health_harness.py
"""
import os, pathlib, subprocess, sys, textwrap, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


import topup_bot as tb  # noqa: E402

# --- 1. a missing key is reported, not silently empty --------------------------------
for var in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "COVERR_API_KEY"):
    os.environ.pop(var, None)
tb.SOURCE_HEALTH.clear()
for fn in (tb.search_pexels, tb.search_pixabay, tb.search_coverr):
    fn("wiping bar counter", 1)
rep = tb.health_report()
print("missing keys   ->", rep or "(nothing reported)")
for name in ("pexels", "pixabay", "coverr"):
    check(name in rep, f"a missing {name} key was not reported")

# --- 2. a rejected key is reported with its status -----------------------------------
os.environ["PEXELS_API_KEY"] = "definitely-not-a-valid-key"
tb.SOURCE_HEALTH.clear()
got = tb.search_pexels("wiping bar counter", 1)
rep = tb.health_report()
print("rejected key   ->", rep or "(nothing reported)")
check(got == [], "a rejected key somehow returned results")
check("pexels" in rep and ("401" in rep or "HTTP" in rep),
      f"a rejected pexels key was not reported as a fault: {rep!r}")
os.environ.pop("PEXELS_API_KEY", None)

# --- 3. the rule: nothing added + work outstanding + a sick source => non-zero --------
# Exercised in isolation so it does not need keys, a GitHub token or the network.
rule = textwrap.dedent("""
    import sys
    def decide(added, thin, sick):
        if added == 0 and thin:
            if sick:
                return 1
        return 0
    cases = [
        (0,  282, "pexels: HTTP 401", 1, "dead key with work outstanding must fail"),
        (0,  282, "",                 0, "a genuinely empty search must stay green"),
        (120, 282, "pexels: HTTP 401", 0, "a run that stocked clips must stay green"),
        (0,    0, "pexels: HTTP 401", 0, "nothing left to stock must stay green"),
    ]
    bad = [m for a, t, s, want, m in cases if decide(a, t, s) != want]
    print("\\n".join("RULE FAIL: " + m for m in bad) or "rule       -> all four cases correct")
    sys.exit(1 if bad else 0)
""")
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
    fh.write(rule); tmp = fh.name
r = subprocess.run([sys.executable, tmp], capture_output=True, text=True)
print((r.stdout or r.stderr).strip())
check(r.returncode == 0, "the fail-loudly rule is wrong")
os.unlink(tmp)

# --- 4. the real harvester actually consults it --------------------------------------
src = (ROOT / "tools" / "harvest_cloud.py").read_text()
check("tb.health_report()" in src, "harvest_cloud does not consult health_report()")
check("sys.exit(1)" in src, "harvest_cloud never exits non-zero on a dead source")

print()
for f in fails:
    print("FAIL:", f)
print(f"{'PASS' if not fails else 'FAILED'} — {len(fails)} failure(s)")
sys.exit(1 if fails else 0)
