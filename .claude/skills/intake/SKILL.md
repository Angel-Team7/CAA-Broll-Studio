---
name: intake
description: Bring new or changed lesson scripts from the Google Drive folder onto cockpit cards (lines, briefs, timing, shot lists) and commit. Hourly routine; never gathers footage.
---

# Intake

## Drive
Root folder `18rEKveDRg6tMROkDXyQETFzW9th4aOLm` ("Video Course Scripts"): `Belong/`,
`Edenrise — Course 1/`, `Edenrise — Course 2/`, one folder per module, docs named
`<Title> — EN` / `<Title> — PT`. List with `search_files` (`parentId = '<id>'`), recursing.

## State
`library/drive_seen.json` maps doc id → modifiedTime last processed. New or changed =
absent or newer. Record PT docs too, but only EN docs are carded for now.

## Per new or changed EN doc
1. `read_file_content` → write to a temp file.
2. Slug: match the folder name to a title in `projects.json`; else create
   `edenrise-c2-m<n>-<kebab>` / `belong-module<n>` / `<kebab>`; title pattern
   "Edenrise C2 — M<n>: <Title>" / "Belong — Module <n>: <Title>" / "Edenrise C1 — <Title>".
3. `python3 tools/script_to_card.py <slug> <tempfile> --title "<title>"` — handles SCENE
   headers and plain prose; leaves a card alone when it already carries the narration.
4. If any scene of that card has no `shots`, follow `.claude/skills/shot-list/SKILL.md`
   and apply the shot list.
5. Record the doc in `library/drive_seen.json`.

## Commit
Only `projects/**/scenes.json`, `projects.json`, `library/drive_seen.json`. User
`intake-bot <bot@edenrise.com>`. Message `[intake-bot] <n> script(s) from Drive: <slugs>`.
Push to main; rebase and retry up to 5 times. Report one paragraph: docs seen, cards
created or updated, cards left authoritative, anything skipped and why.
