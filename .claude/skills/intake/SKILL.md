---
name: intake
description: Bring new or changed lesson scripts from the Google Drive folder onto cockpit cards (lines, briefs, timing, shot lists) and commit. Hourly routine; never gathers footage.
---

# Intake

## Drive
Root folder `18rEKveDRg6tMROkDXyQETFzW9th4aOLm` ("Video Course Scripts"). One top-level
folder per client or department — today `Belong/`, `Edenrise — Course 1/`,
`Edenrise — Course 2/` — then one folder per module, docs named `<Title> — EN` /
`<Title> — PT`. List with `search_files` (`parentId = '<id>'`), recursing.

A **new top-level folder is a new client or department**. Card its scripts as usual, and
give them a sector (below). Never skip a folder just because it is not one of the two
original clients — that is the whole point of the sector model.

## State
`library/drive_seen.json` maps doc id → modifiedTime last processed. New or changed =
absent or newer. Record PT docs too, but only EN docs are carded for now.

## Per new or changed EN doc
1. `read_file_content` → write to a temp file.
2. Slug: match the folder name to a title in `projects.json`; else create
   `edenrise-c2-m<n>-<kebab>` / `belong-module<n>` / `<kebab>`; title pattern
   "Edenrise C2 — M<n>: <Title>" / "Belong — Module <n>: <Title>" / "Edenrise C1 — <Title>".
3. **Sector.** Every card belongs to a sector (`sectors.json`; see CLAUDE.md). Run
   `python3 tools/sectors.py` for the list. Edenrise folders → `edenrise`, Belong →
   `belong`. For a folder that is neither, pick the sector whose `world` actually matches
   the work the script is about — an internal-comms course for an accountancy firm is
   `finance`, a care-home induction is `healthcare`, a head-office course is `office`. If
   nothing fits, use `universal` and say so in the report so a sector can be written for
   them; **do not invent a sector id** and do not edit `sectors.json` during intake.
4. `python3 tools/script_to_card.py <slug> <tempfile> --title "<title>" --sector <id>` —
   handles SCENE headers and plain prose; leaves a card alone when it already carries the
   narration. The sector is recorded in `projects.json` and drives every later stage; a
   card carded without one silently inherits Edenrise's never-list.
5. If any scene of that card has no `shots`, follow `.claude/skills/shot-list/SKILL.md`
   and apply the shot list — written in that card's sector world, not Edenrise's.
6. Record the doc in `library/drive_seen.json`.

## Commit
Only `projects/**/scenes.json`, `projects.json`, `library/drive_seen.json`.
Never `sectors.json`. User
`intake-bot <bot@edenrise.com>`. Message `[intake-bot] <n> script(s) from Drive: <slugs>`.
Push to main; rebase and retry up to 5 times. Report one paragraph: docs seen, cards
created or updated with their sectors, cards left authoritative, any folder that had no
fitting sector, anything skipped and why.
