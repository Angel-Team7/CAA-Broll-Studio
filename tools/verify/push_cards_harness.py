#!/usr/bin/env python3
"""Prove push_cards.py survives the collision that lost 181 staged clips.

Builds a throwaway repo with a bare "origin", then reproduces the real failure: a topup
appends candidates to a card while, mid-run, the judge pushes verdicts to the SAME card
and file. The old push step rebased, hit a content conflict, aborted five times and threw
the work away. This asserts the replay keeps both sides:

  * the judge's verdicts on the clips it judged      (not reverted)
  * every candidate the topup staged                  (not lost)
  * the client's approvals exactly as origin has them (never written by this path)

Then it runs the collision the other way round — the judge replaying verdicts while a
topup has pushed fresh candidates underneath it — because a replay that only appended
clips would silently drop every score the judge spent a session producing. That is the
shape of the real failure on belong-action-m1: 182 clips judged, then back to awaiting.

    python3 tools/verify/push_cards_harness.py
"""
import json, pathlib, shutil, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve()
PUSH_CARDS = HERE.parent.parent / "push_cards.py"
fails = []


def sh(*a, cwd, check=True):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"! {' '.join(a)} in {cwd}\n{r.stdout}\n{r.stderr}")
    return r


def card(clips):
    return {"slug": "demo", "title": "Demo", "scenes": [
        {"id": "S01", "script_line": "a line", "shots": [{"id": "A", "text": "t",
         "pexels": "t", "pixabay": "t", "scale": "wide"}], "must_not": [], "clips": clips}]}


def clip(i, **kw):
    c = {"id": f"pexels_{i}_demo", "source": "pexels", "src_id": str(i),
         "preview": f"http://x/{i}.mp4", "thumb": f"http://x/{i}.jpg"}
    c.update(kw); return c


def check(cond, msg):
    if not cond:
        fails.append(msg)


tmp = pathlib.Path(tempfile.mkdtemp(prefix="push-cards-harness-"))
try:
    origin, work = tmp / "origin.git", tmp / "work"
    sh("git", "init", "-q", "--bare", str(origin), cwd=tmp)
    sh("git", "clone", "-q", str(origin), str(work), cwd=tmp)
    sh("git", "config", "user.name", "t", cwd=work)
    sh("git", "config", "user.email", "t@t", cwd=work)
    (work / "tools" / "verify").mkdir(parents=True)
    shutil.copy(PUSH_CARDS, work / "tools" / "push_cards.py")
    (work / "projects" / "demo").mkdir(parents=True)
    (work / "selections").mkdir()

    # --- origin starts with two staged clips and one client approval ------------------
    base = card([clip(1, judged=False), clip(2, judged=False)])
    json.dump(base, open(work / "projects/demo/scenes.json", "w"), indent=1)
    json.dump({"project": "demo", "approved": {"S01": ["pexels_1_demo"]},
               "needs_broll": {}, "topup_requests": {}},
              open(work / "selections/demo.json", "w"), indent=2)
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-q", "-m", "base", cwd=work)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=work)
    sh("git", "branch", "-q", "-M", "main", cwd=work)
    sh("git", "branch", "-q", "--set-upstream-to=origin/main", "main", cwd=work)

    # --- the judge pushes verdicts on those two clips, from somewhere else ------------
    other = tmp / "judge"
    sh("git", "clone", "-q", str(origin), str(other), cwd=tmp)
    sh("git", "config", "user.name", "judge", cwd=other)
    sh("git", "config", "user.email", "j@j", cwd=other)
    judged = card([clip(1, judged=True, relevance=9, brand_fit=8, caption="a real caption",
                        rank=1, shown=True),
                   clip(2, judged=True, relevance=3, brand_fit=5, caption="weak one",
                        rank=2, shown=False)])
    judged["scenes"][0]["stock_gap"] = True
    json.dump(judged, open(other / "projects/demo/scenes.json", "w"), indent=1)
    sh("git", "add", "-A", cwd=other)
    sh("git", "commit", "-q", "-m", "[judge-bot] judged 1 scene", cwd=other)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=other)

    # --- meanwhile the topup, working from the OLD base, appends four candidates ------
    staged = card([clip(1, judged=False), clip(2, judged=False),
                   clip(3, judged=False), clip(4, judged=False),
                   clip(5, judged=False), clip(6, judged=False)])
    json.dump(staged, open(work / "projects/demo/scenes.json", "w"), indent=1)
    sel = json.load(open(work / "selections/demo.json"))
    sel["topup_requests"]["S01"] = {"requested": "now", "done": True, "added": 4}
    json.dump(sel, open(work / "selections/demo.json", "w"), indent=2)

    # a plain rebase here is what failed in production — confirm it still does
    sh("git", "add", "-A", cwd=work)
    sh("git", "commit", "-q", "-m", "[topup-bot] +4", cwd=work)
    sh("git", "fetch", "-q", "origin", "main", cwd=work)
    reb = sh("git", "rebase", "origin/main", cwd=work, check=False)
    check(reb.returncode != 0, "the old rebase path did NOT conflict — harness no longer "
                               "reproduces the production failure")
    print(f"old path: rebase {'conflicted (as in production)' if reb.returncode else 'succeeded'}")
    sh("git", "rebase", "--abort", cwd=work, check=False)
    sh("git", "reset", "-q", "--soft", "HEAD~1", cwd=work)      # back to uncommitted changes

    # --- now the replay ---------------------------------------------------------------
    r = subprocess.run([sys.executable, "tools/push_cards.py", "[topup-bot] +4 candidates"],
                       cwd=work, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    check(r.returncode == 0, f"push_cards exited {r.returncode}")

    final = json.loads(sh("git", "show", "origin/main:projects/demo/scenes.json",
                          cwd=work).stdout)
    fsel = json.loads(sh("git", "show", "origin/main:selections/demo.json", cwd=work).stdout)
    sc = final["scenes"][0]
    ids = [c["id"] for c in sc["clips"]]
    by = {c["id"]: c for c in sc["clips"]}

    check(len(ids) == 6, f"expected 6 clips on the card, found {len(ids)}: {ids}")
    for i in (3, 4, 5, 6):
        check(f"pexels_{i}_demo" in by, f"staged clip {i} was LOST")
    check(by.get("pexels_1_demo", {}).get("caption") == "a real caption",
          "the judge's caption on clip 1 was reverted")
    check(by.get("pexels_1_demo", {}).get("relevance") == 9,
          "the judge's score on clip 1 was reverted")
    check(by.get("pexels_2_demo", {}).get("shown") is False,
          "the judge's hide on clip 2 was reverted")
    check(sc.get("stock_gap") is True, "the judge's stock_gap on the scene was reverted")
    check(fsel["approved"] == {"S01": ["pexels_1_demo"]},
          f"approvals changed: {fsel['approved']}")
    check(fsel["topup_requests"].get("S01", {}).get("done") is True,
          "the top-up request was not marked fulfilled")

    # ---------------------------------------------------------------------------------
    # Round two, the other direction: the JUDGE replays verdicts while a topup has
    # meanwhile pushed fresh candidates. A pure append would drop every score. This is
    # what actually happened on belong-action-m1: 182 clips judged, then reverted to
    # awaiting, because the judge hand-rebased over another push.
    print("\n-- judge direction --")
    topup = tmp / "topup2"
    sh("git", "clone", "-q", str(origin), str(topup), cwd=tmp)
    sh("git", "config", "user.name", "topup", cwd=topup)
    sh("git", "config", "user.email", "t@t", cwd=topup)
    more = json.load(open(topup / "projects/demo/scenes.json"))
    more["scenes"][0]["clips"].append(clip(7, judged=False))
    json.dump(more, open(topup / "projects/demo/scenes.json", "w"), indent=1)
    sh("git", "add", "-A", cwd=topup)
    sh("git", "commit", "-q", "-m", "[topup-bot] +1 while the judge works", cwd=topup)
    sh("git", "push", "-q", "origin", "HEAD:main", cwd=topup)

    # the judge, working from before that push, writes verdicts on clips 3-6
    sh("git", "fetch", "-q", "origin", "main", cwd=work)
    sh("git", "reset", "-q", "--hard", "HEAD", cwd=work)
    judge_copy = json.load(open(work / "projects/demo/scenes.json"))
    for c in judge_copy["scenes"][0]["clips"]:
        if c["id"] in {f"pexels_{i}_demo" for i in (3, 4, 5, 6)}:
            c.update({"judged": True, "relevance": 8, "brand_fit": 7,
                      "caption": f"judged {c['id']}", "rank": 3, "shown": True})
    json.dump(judge_copy, open(work / "projects/demo/scenes.json", "w"), indent=1)

    r2 = subprocess.run([sys.executable, "tools/push_cards.py",
                         "[judge-bot] judged 1 scene(s): demo/S01"],
                        cwd=work, capture_output=True, text=True)
    print(r2.stdout.strip() or r2.stderr.strip())
    check(r2.returncode == 0, f"judge-direction push_cards exited {r2.returncode}")

    final2 = json.loads(sh("git", "show", "origin/main:projects/demo/scenes.json",
                           cwd=work).stdout)
    by2 = {c["id"]: c for c in final2["scenes"][0]["clips"]}
    for i in (3, 4, 5, 6):
        cid = f"pexels_{i}_demo"
        check(by2.get(cid, {}).get("judged") is True, f"the judge's verdict on {cid} was LOST")
        check(by2.get(cid, {}).get("caption") == f"judged {cid}",
              f"the judge's caption on {cid} was LOST")
    check("pexels_7_demo" in by2, "the concurrent topup's clip 7 was LOST")
    check(by2.get("pexels_1_demo", {}).get("caption") == "a real caption",
          "an earlier verdict on clip 1 was overwritten by the stale copy")
    check(by2.get("pexels_1_demo", {}).get("relevance") == 9,
          "an earlier score on clip 1 was overwritten by the stale copy")

    print()
    for f in fails:
        print("FAIL:", f)
    print(f"{'PASS' if not fails else 'FAILED'} — {len(fails)} failure(s)")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
