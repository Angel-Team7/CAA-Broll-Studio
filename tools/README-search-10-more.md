# 🔎 Search 10 more — automated

Clicking **Search 10 more** on a cockpit card writes a `topup_request` into
`selections/<slug>.json`. That commit triggers `.github/workflows/search-10-more.yml`,
which fetches 10 fresh video candidates for that scene on GitHub's servers and commits
them back. New options appear on the card a few minutes later — no Mac, no chat.

## One-time setup — add the API keys as repo Secrets

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Add these three (names must match exactly):

| Secret name | Where it comes from |
|---|---|
| `PEXELS_API_KEY`  | pexels.com/api |
| `PIXABAY_API_KEY` | pixabay.com/api/docs |
| `COVERR_API_KEY`  | coverr.co/api |

To print your existing values locally:

    grep -E 'PEXELS|PIXABAY|COVERR' ~/Broll-Studio/config/.env

Secrets are never exposed in logs or to forks. Until they are set the Action still runs,
falling back to keyless Wikimedia Commons — far fewer and weaker results.

## What it does / does not do

- **Does**: 10 fresh videos per request, round-robin across Pexels/Pixabay/Coverr so no
  single library fills the batch; skips anything already on the card (by source id and
  page URL); starts deep in the result pages so you get new material, not page 1 again;
  builds a 480p preview (20s cap) + thumb; appends to `scenes.json`; appends attribution
  to the project's `CREDITS.md`; marks the request `done`.
- **Does not**: curate. These are raw candidates — you are the curator at that moment.
  A taste filter removes the known junk classes (end-cards, cartoons, green screen,
  wildlife, flowers, abstract texture, office/corporate, ruins). Anything with tags must
  positively show a person, their hands, or their work to be admitted at all.
- **Masters are never committed.** Each clip records `source`, `src_id`, `page_url` and
  `download_url`, so the full-resolution file is re-fetchable by id at render time.
  That keeps the repo (already ~2 GB of previews) from growing fast.

New clips carry a green **NEW** badge in the cockpit until you act on them.

## Safety rails

- `concurrency: search-10-more` — runs queue, so two clicks can never rewrite the same
  `scenes.json` at once.
- The job skips its own commits (`[topup-bot]`), so it cannot loop.
- Sparse checkout (`selections`, `tools`, `.github` + the one project it touches) keeps
  the 2 GB repo from being cloned in full on every run.
- Push retries with rebase 5× in case a human pushes at the same moment.
- Max 8 scenes per run; anything beyond that is reported and picked up on the next run.

## Manual run

Actions tab → **Search 10 more** → **Run workflow**. It processes every pending request
in `selections/`, so it doubles as a catch-up if a click was missed.

## Tuning

Edit the `TOPUP_VIDEOS` env in the workflow (default 10). The taste lists live at the top
of `topup_bot.py` — `POSITIVE` is the earn-your-place vocabulary, `JUNK` / `EDENRISE_BLOCK`
/ `BELONG_BLOCK` are the exclusions. Profile is chosen from the slug (`belong-*` vs the rest).
