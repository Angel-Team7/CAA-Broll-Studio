# B-roll Cockpit — how every Claude session works here

This repo is the brain of the B-roll pipeline. It serves any number of clients and
departments through the sector registry. Any Claude session that
clones it (a cloud routine, a Mac session, a one-off run) follows this file. Procedures
live in `.claude/skills/*/SKILL.md`; read the skill before doing its job.

## The goal, in one line
**The right ten clips on every beat**: footage that shows what the viewer hears, in the
sector's world, ranked and captioned before a reviewer sees it. Measured by ticks.

## Sectors (taste laws — these override any stock result)

The studio is not two clients. Every world it gathers for is a **sector**, declared in
`sectors.json` at the repo root: a `name`, the `world` in prose, a `never` list of barred
words, the `positive` vocabulary a clip must show to earn its place, query `prefix`/`tail`
flavour, and `seeds` — the beats the harvester shops so a sector is stocked before its
first lesson exists. Adding a client or a department is a registry entry, not a code change.

A project names its sector in `projects.json` (`"sector": "office"`). With none named the
legacy rule still holds (`belong-*` → belong, anything else → edenrise), so no existing
card changed behaviour when sectors landed.

    python3 tools/sectors.py                  # every sector
    python3 tools/sectors.py <slug>           # a card's sector, world and never-list
    python3 tools/sectors.py --check          # every card, and any unknown sector name

Sectors today: `universal`, `edenrise`, `belong`, `office`, `hospitality`, `healthcare`,
`retail`, `logistics`, `manufacturing`, `construction`, `education`, `finance`,
`field-service`, `agriculture`, `tech`.

**Read the sector, never assume.** A word barred in one sector is the subject of another:
Edenrise bars `office`, `laptop` and `meeting`; the office sector is built on them.
`tools/sectors.py <slug>` prints the law that actually applies — nothing is hardcoded.

The two client sectors carry extra valence rules a registry cannot hold:
- **Edenrise** — a negative line ("things become invisible", "below the line") wants a
  neutral or troubled frame, not smiling crews. Lines about being seen, thanked or noticed
  need a face. Openers are warm establishing shots, never an intense portrait. No
  "gangster" signifiers (intense stare into camera, hoodie, behind bars, dark industrial
  workshops) and no forced-labour framing. The team is African.
- **Belong** — complaints, mistakes and difficult guests are shown with composure and
  listening, never with anger theatre. Authentic, not luxury.
- **Any sector** — a negative or difficult line wants a frame that matches it. The judge
  caps a smiling stock crew on a hard line at `brand_fit` 4.

## The shared shelf is shared
`library/index.json` is one shelf for every sector, not a partition per client. A clip of
two people talking something through serves an office lesson as well as the Edenrise beat
it was harvested for. Admission is decided by the sector's own law — clear the `never`
list, show the `positive` vocabulary, and match the beat's shot **action** — with a
preference, not a lock, for footage already proven in that sector.

## The card model (`projects/<slug>/scenes.json`)
Per scene: `id` (S01…), `script_line` (what the viewer hears, verbatim), `visual_direction`
(the brief), `onscreen`, `t`/`end`, `timing_source` (narration | estimated | unrecorded),
`shots[]` (the shot list — see the shot-list skill), `must_not[]`, `clips[]`.
Per clip: `id`, `type`, `source`, `src_id`, `page_url`, `download_url`, `preview`, `thumb`
(both on GitHub Releases), `query`, `title`, plus judge fields: `judged`, `relevance`,
`brand_fit` (the sector-fit score — the field name predates sectors and is kept so no
card has to be rewritten), `caption`, `violation`, `rank`, `shown`, `strip`.

## Rules that are never broken
1. **Never edit `selections/*.json` approvals.** Automation appends candidates and judge
   fields on cards; only a human ticks or unticks. Ticks are training data.
   **A tick must never be lost and never move.** An approved clip stays on the card and on
   the scene it was approved for, whatever else changes — culls, renumbers, re-gathers and
   judge passes all skip it. After any operation that removes or renumbers clips, run
   `python3 tools/recover_approvals.py --dry`; it restores approved footage to its own
   scene by source id or page_url and reports anything it cannot find.
2. **Never commit media.** Previews and thumbs go to Releases through
   `tools/release_media.py`; the cockpit reaches them through the media proxy.
3. **Never change a slug.** Selections key on slugs. Titles may change.
4. **Never invent a spoken line.** If narration is not recorded, say so on the card.
5. **Never pad.** A beat with fewer than three clips that clear the judge is marked
   `stock_gap` with the reason, not filled with junk.
6. **Never touch `belong-module7`** (work in progress, off-limits).

## Pipeline map (two hops)
1. **Intake** (routine, hourly): Drive script → card with lines, briefs, shot lists.
2. **Recall + stage** (GitHub Action on a click): shot phrasings → Pexels/Pixabay/Coverr →
   ~150 candidates → shortlist 24 → previews, thumbs, 3-frame strips uploaded →
   clips appended to the card with `judged:false`.
3. **Judge** (routine, fired by the push): reads strips, scores against the beat's shot
   list and the card's SECTOR rules, captions, ranks, shows the top ten, appends verdicts
   to `library/verdicts.jsonl`.
4. **Cockpit** (GitHub Pages): ranked grid, captions, shot list, status line.
Harvester (Action, hourly) stocks the shared library the same way, without a click:
real cards' beats first, then every sector's `seeds`, so a new sector fills up before it
has a lesson.

## Commit tags (loop guards)
`[intake-bot]`, `[topup-bot]`, `[harvest-bot]`, `[judge-bot]`. Workflows skip their own tags.
Every job is idempotent: re-running it must not duplicate clips or verdicts.

## Verify before depending
Harnesses live in `tools/verify/`. New hosts, players, triggers or APIs get a harness
before the pipeline relies on them (the Cloudflare worker, Safari playback and the
routine webhook were all verified this way).
