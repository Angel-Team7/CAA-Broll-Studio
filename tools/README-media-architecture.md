# Media architecture — how the cockpit stays light

**The site is the viewer, not the store.**

| Layer | Where | Size | Why |
|---|---|---|---|
| Cockpit (cards, approvals, app) | git repo → GitHub Pages | ~4 MB | deploys in about a minute; every change ships only the change |
| 480p previews + thumbnails | GitHub **Releases**, one per lesson (`media-<slug>`) and one shared (`media-library`) | ~2.2 GB | outside the git object database — clones, Actions checkouts and Pages deploys never touch them; free; range requests supported |
| Full-resolution masters | the SSD (`/Volumes/Ultra Touch/Broll-Masters`) | as needed | never in the cloud; fetched **on approval** by source id with `tools/fetch_masters.py` before a render |
| Shared library index | `library/index.json` in git | ~2 MB | facets (subjects / actions / setting / scale / people / brand) for every owned clip; what 🔎 searches first |
| Scripts | Google Drive folder `Video Course Scripts` (`18rEKveDRg6tMROkDXyQETFzW9th4aOLm`) | — | the source of truth for narration; `Belong/`, `Edenrise — Course 1/`, `Edenrise — Course 2/`, one folder per module, docs named `<Title> — EN` / `<Title> — PT` |

## Rules
- **Never commit media.** `.gitignore` blocks `projects/*/previews/` and `projects/*/thumbs/`. All publishers and the bots write through `tools/release_media.py`.
- Asset names are `<scene>__<kind>__<file>` so a preview and its thumb can never collide. GitHub normalises names (runs of dots collapse to one) — always store the URL the API returns, never a constructed one.
- Uploads are serial with backoff. Parallel uploads trip GitHub's secondary rate limit.
- Masters are fetched, not stored: only approved clips ever get one, and only onto the SSD.
- Nothing automated ever edits `selections/` or a scene's `clips` array in place. Bots only append candidates.
- Slugs are permanent. Rename titles in `projects.json`; never the slug.

## Jobs

| Job | Runs where | Trigger | Does |
|---|---|---|---|
| **Script intake** (`tools/script_to_card.py`) | Claude cloud routine "B-roll script intake — Drive → cockpit", hourly, every day (minute 17) | schedule | reads the Drive folder through the Google Drive connector, cards every new/changed EN doc that has `SCENE` headers, records what it saw in `library/drive_seen.json`, commits `[intake-bot]`. Plain-prose docs (no SCENE structure) are skipped and named in the run report — it never guesses a split. Clips untouched. |
| **Harvest** (`tools/harvest_cloud.py`, `.github/workflows/harvest.yml`) | GitHub Action | hourly, every day + any `scenes.json` push | stocks the shared library by every beat on every card, thin beats first, so clicks promote off the shelf instead of hitting the internet. Budgeted per run (30 clips, thin beats first); masters never stored. Each run appends one line to `library/harvest_log.jsonl` — the week's stocking record. |
| **Search 10 more / Direction is wrong** (`tools/topup_bot.py`, `.github/workflows/search-10-more.yml`) | GitHub Action | a click (push to `selections/**.json`) | see `README-search-10-more.md` |
| `tools/fetch_masters.py` | the Mac | before a render | downloads the master of every approved clip to the SSD |

### Access the jobs need
- **Actions**: repo Secrets `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `COVERR_API_KEY` (set once in Settings → Secrets → Actions).
- **Intake routine**: the Claude GitHub App must be installed on the `Angel-Team7` org with access to
  `CAA-Broll-Studio` (https://github.com/apps/claude/installations/select_target). Without it the
  routine reads Drive fine but every push is refused with 403 and the commit is lost with the sandbox.
  Manage the routine at https://claude.ai/code/routines .
- **Workflow files** need a token with `workflow` scope to push. The everyday push token does not
  have it. Stage new or edited yml under `tools/workflows-pending/` and run the routine
  "Cockpit — install workflow files" (https://claude.ai/code/routines); the Claude GitHub App has the
  permission and moves them into `.github/workflows/`.

## Safari and the media proxy
GitHub serves Release assets as `application/octet-stream` with sniffing disabled and no CORS.
Chrome and Firefox sniff the bytes and play the previews anyway; **Safari refuses** to play media
not labelled as media, so on Safari hover and ▶ do nothing and a toast says so. The fix is a
free Cloudflare Worker that re-serves the same files as `video/mp4` / `image/jpeg` with byte
ranges and CORS — `tools/media-proxy.worker.js`, tested against real assets.

Set-up (once, ~3 minutes, on the Cloudflare account):
1. dash.cloudflare.com → **Workers & Pages** → **Create** → **Hello World** → name it `broll-media` → Deploy.
2. **Edit code** → replace everything with the contents of `tools/media-proxy.worker.js` → **Deploy**.
3. Copy the worker URL (`https://broll-media.<account>.workers.dev`) and put it in `projects.json`
   as `"media_proxy": "https://broll-media.<account>.workers.dev"` (or send it to Vic).
The cockpit then routes every preview and thumbnail through the proxy for every browser; the
Releases stay the store. Free plan: 100k requests/day, no bandwidth charge, edge-cached.

## Adding a lesson
1. Put the script in the right Drive folder as `<Title> — EN`, using `SCENE n —` headers with
   `HEYGEN AVATAR`, `B-ROLL:` and `ON SCREEN TEXT:` blocks. The intake routine cards it within the hour
   (or run the routine now from the routines page).
2. The card commit fires the harvester; first candidates appear on the card in a few minutes.
3. Once narration is recorded, re-time the card from `timing.json` so VIEWER HEARS goes from `≈` to `✓`.

## Still to do
- Rewrite git history to drop the old 2.2 GB of blobs (deploys already ignore them; clones do not).
  Do this deliberately, with a backup, when nothing else is in flight.
