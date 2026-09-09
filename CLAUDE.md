# B-roll Cockpit — how every Claude session works here

This repo is the brain of the B-roll pipeline for two clients. Any Claude session that
clones it (a cloud routine, a Mac session, a one-off run) follows this file. Procedures
live in `.claude/skills/*/SKILL.md`; read the skill before doing its job.

## The goal, in one line
**The right ten clips on every beat**: footage that shows what the viewer hears, in the
brand's world, ranked and captioned before a reviewer sees it. Measured by ticks.

## The two brands (taste laws — these override any stock result)

### Edenrise (slugs without `belong-`)
Soft-skills lessons for land and hands workers at a wellness resort; the team is African.
- **World:** grounds-keeping, landscaping, gardening, greenhouse, orchard, vineyard, small
  building repair, carpentry, painting, pruning, hands in soil, a foreman guiding one
  apprentice, two crew talking by a wheelbarrow. Calm, dignified, single people or pairs.
- **Never:** offices, laptops, suits, boardrooms, whiteboards; factories, assembly lines,
  textile mills, crowds doing the same manual task; scaffolding gangs, welding sparks;
  cartoons, green screen, abstract loops, wildlife, flowers-only, ruins/abandoned; face
  masks; "gangster" signifiers (intense stare into camera, hoodie, behind a fence or bars,
  boxing gyms, dark industrial workshops); forced-labour or slave-like framing.
- **Valence:** a negative line ("things become invisible", "below the line") wants a
  neutral or troubled frame, not smiling crews. Lines about being seen, thanked or
  noticed need a face. Openers are warm establishing shots, never an intense portrait.

### Belong (slugs `belong-*`) — Craveiral Farmhouse, Alentejo
Hospitality lessons for a farmhouse hotel. Authentic, warm, tactile, nature-rooted,
community and circular economy. **Not luxury.**
- **World:** small guesthouse reception, host welcoming a guest at a door, farm table,
  kitchen with local produce, garden, orchard, vegetable rows, a waiter at a wooden table,
  housekeeping with care, hands with cherries or bread, sunset over fields, Alentejo light.
- **Never:** corporate hotel chains, glass lobbies, resort pools and beaches, luxury
  spa clichés, business suits, construction and building trades, factories, warehouses,
  sewing and industry, face masks, stock "customer service" call centres.
- **Valence:** complaints, mistakes and difficult guests are shown with composure and
  listening, never with anger theatre.

## The card model (`projects/<slug>/scenes.json`)
Per scene: `id` (S01…), `script_line` (what the viewer hears, verbatim), `visual_direction`
(the brief), `onscreen`, `t`/`end`, `timing_source` (narration | estimated | unrecorded),
`shots[]` (the shot list — see the shot-list skill), `must_not[]`, `clips[]`.
Per clip: `id`, `type`, `source`, `src_id`, `page_url`, `download_url`, `preview`, `thumb`
(both on GitHub Releases), `query`, `title`, plus judge fields: `judged`, `relevance`,
`brand_fit`, `caption`, `violation`, `rank`, `shown`, `strip` (contact strip URL).

## Rules that are never broken
1. **Never edit `selections/*.json` approvals.** Automation appends candidates and judge
   fields on cards; only a human ticks or unticks. Ticks are training data.
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
3. **Judge** (routine, fired by the push): reads strips, scores, captions, ranks, shows
   the top ten, appends verdicts to `library/verdicts.jsonl`.
4. **Cockpit** (GitHub Pages): ranked grid, captions, shot list, status line.
Harvester (Action, hourly) stocks the shared library the same way, without a click.

## Commit tags (loop guards)
`[intake-bot]`, `[topup-bot]`, `[harvest-bot]`, `[judge-bot]`. Workflows skip their own tags.
Every job is idempotent: re-running it must not duplicate clips or verdicts.

## Verify before depending
Harnesses live in `tools/verify/`. New hosts, players, triggers or APIs get a harness
before the pipeline relies on them (the Cloudflare worker, Safari playback and the
routine webhook were all verified this way).
