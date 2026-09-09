# 🔎 Need more · 🔁 Direction is wrong — automated

Both buttons on a cockpit card are one click, no dialog. Each writes a request into
`selections/<slug>.json`; that commit triggers `.github/workflows/search-10-more.yml`, which
finds 10 fresh video candidates for that scene on GitHub's servers and commits them back.
New options appear under the existing ones a few minutes later — no Mac, no chat.

| Button | Request | What the bot does |
|---|---|---|
| **🔎 Need more** | `topup_request` | more of the *same* kind. Library first, then the internet. Reads "10 more queued" only while the request is unfulfilled; once the clips land it is clickable again. |
| **🔁 Direction is wrong** | `reshoot` with `reason:"direction"` | a *different* kind. Skips the library, lets the reviewer's note lead the query, and carries an **avoid** list built from the words that describe what is already on the card. Clicking again on a flagged scene ("Still wrong — 10 more") fires another search that also avoids the new batch; the flag itself is removed only with the **clear flag** link under the brief. |

The reviewer's note is parsed: `less X` / `no X` / `too X` become avoid terms, "not
contextual for X" chases X, and request filler ("please generate 10 more", "delete these")
is dropped so it never becomes a search term.

## Library first
`library/index.json` holds every clip we already own, faceted by subject, action, setting,
scale, people and brand. A 🔎 click first promotes matching library clips whose *action*
matches the beat (at most 40 % of the batch), then fills the rest from the internet. That is
why clicks are fast and why footage recurs across lessons in a consistent voice. The library
is stocked hourly by `harvest.yml`.

## One-time setup — API keys as repo Secrets

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

| Secret name | Where it comes from |
|---|---|
| `PEXELS_API_KEY`  | pexels.com/api |
| `PIXABAY_API_KEY` | pixabay.com/api/docs |
| `COVERR_API_KEY`  | coverr.co/api |

Secrets are never exposed in logs or to forks. Without them the Action still runs, falling
back to keyless Wikimedia Commons — far fewer and weaker results.

## What it does / does not do

- **Does**: 10 fresh videos per request, round-robin across Pexels / Pixabay / Coverr so no
  single source fills the batch; skips anything already on the card (by source id and page
  URL); starts deep in the result pages; builds a 480p preview (20 s cap) + thumb and uploads
  them to the lesson's Release; appends to `scenes.json` with a green **NEW** badge; appends
  attribution to the project's `CREDITS.md`; marks the request `done`.
- **Does not**: curate, or touch ticks. These are raw candidates — the reviewer is the curator.
  An evidence-based taste filter admits a clip only if its title or tags positively show a
  person, their hands, or their work, and rejects the known junk classes (end-cards, cartoons,
  green screen, wildlife, flowers, abstract texture, office/corporate, ruins, factory crowds).
  Profile is chosen from the slug: `belong-*` (warm Alentejo hospitality) vs Edenrise
  (land and hands workers).
- **Masters are never committed.** Each clip records `source`, `src_id`, `page_url` and
  `download_url`; the full-resolution file is fetched per approved clip at render time.

## Safety rails

- `concurrency: search-10-more` — runs queue, so two clicks never rewrite the same `scenes.json`.
- The job skips its own commits (`[topup-bot]`) and the harvester's (`[harvest-bot]`), so it cannot loop.
- Sparse, blobless checkout of `selections`, `tools`, `library`, `.github` plus the one project it touches.
- Push retries with rebase 5× in case a human saves at the same moment.
- Max 8 scenes per run; when more are waiting the run re-queues itself, so a long backlog drains on its own.
- The bot gets the Actions token for release uploads; a bot failure fails the run (no green runs with 0 added).
- ffmpeg comes from a cached static build (`~/ffbin`), apt as fallback, so a run is ~90 s.

## Manual run

Actions tab → **Search 10 more** → **Run workflow**. It processes every pending request in
`selections/`, so it doubles as a catch-up if a click was missed.

## Tuning

`TOPUP_VIDEOS` env in the workflow (default 10). Taste lists live at the top of
`tools/topup_bot.py` — `POSITIVE` is the earn-your-place vocabulary, `JUNK` /
`EDENRISE_BLOCK` / `BELONG_BLOCK` the exclusions. Library share cap is the `TOPUP_LIBRARY_SHARE` env (default 0.4).
