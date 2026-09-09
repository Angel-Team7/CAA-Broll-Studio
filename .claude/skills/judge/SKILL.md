---
name: judge
description: Judge staged B-roll candidates by looking at their frames — score relevance and brand fit against the beat's shot list, caption each clip, rank, show the top ten, mark stock gaps. Runs on every push (webhook); exits in seconds when nothing is pending.
---

# Judge

You are the reviewer's eyes before the reviewer. You look at frames, not tags.

## Step 0 — is there work?
```
python3 tools/judge.py pending
```
Prints `slug scene n_unjudged` lines, or `nothing pending`. If nothing is pending, stop
and report one line. Do not read anything else.

## Step 1 — get the material for one scene
```
python3 tools/judge.py strips <slug> <scene>
```
Downloads every unjudged clip's 3-frame contact strip to a temp folder and prints, per
clip: `clip_id  path  source  title  duration`. It also prints the spoken line, the brief,
the shot list, the must-not list, the brand, and the brand's standing never-list from
`CLAUDE.md`. **Read every strip image** with the Read tool. Judge only what you can see.

## Step 2 — score each clip
- `relevance` 0–10: does it show one of the shots? 9–10 the shot itself; 6–8 the same
  subject and action in a different setting; 3–5 same world, wrong action; 0–2 unrelated.
- `brand_fit` 0–10: is it in the brand's world and free of the never-list? Masks,
  offices, factories, resort pools, cartoons, wildlife: 0. Wrong valence (smiling crew on a
  negative line): at most 4.
- `caption`: one plain line of what the clip shows, 6–14 words, present tense, no
  adjectives about quality ("a receptionist listens to a guest across a wooden desk").
- `violation`: the never-list item it breaks, or empty.
- `shot`: the shot id it best serves, or empty.
- `shoot`: a short key for "same shoot" (same set, same people, same look), so the
  diversity rule can cap it. Use the author plus the set, e.g. "pexels-cottonbro-reception".

## Step 3 — apply
Write `verdicts.json` as `{ "<clip_id>": {relevance, brand_fit, caption, violation, shot, shoot} }` and run
```
python3 tools/judge.py apply <slug> <scene> verdicts.json
```
The tool sets `judged:true` and the fields, computes `score`, ranks all judged clips on
the scene (approved clips always keep `shown:true`), applies diversity (no `shoot` more
than twice in the top ten), shows the top ten, hides the rest (`shown:false`), marks the
scene `stock_gap` with a reason when fewer than three clips reach relevance ≥ 6 with no
violation, and appends every verdict to `library/verdicts.jsonl` and every violation to
`library/rejected.json`.

Repeat Step 1–3 for each pending scene, up to 12 scenes or about 150 clips per run, whichever
comes first; report the remainder (the next push picks it up). A scene with more than 60 pending
clips is fine to judge in one go — read every strip.

## Step 4 — commit
`git config user.name judge-bot && git config user.email bot@edenrise.com`, then commit
only `projects/**/scenes.json` and `library/` with message
`[judge-bot] judged <n> scene(s): <slug/scene, …>` and push to main (rebase and retry up
to 5 times). Never touch `selections/`. Report in three lines: scenes judged, stock gaps
declared, anything skipped.

## What good looks like
Ten clips a reviewer can approve without wading. Three usable is the floor; if the frames
do not reach it, say so — a declared gap is a success, a padded card is a failure.
