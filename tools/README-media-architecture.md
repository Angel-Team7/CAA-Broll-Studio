# Media architecture — how the cockpit stays light

**The site is the viewer, not the store.**

| Layer | Where | Size | Why |
|---|---|---|---|
| Cockpit (cards, approvals, app) | git repo → GitHub Pages | ~4 MB | deploys in ~1 min; every change ships only the change |
| 480p previews + thumbnails | GitHub **Releases**, one per lesson (`media-<slug>`) and one shared (`media-library`) | ~2.2 GB | outside the git object database — clones, Actions checkouts and Pages deploys never touch them; free; range requests supported |
| Full-resolution masters | the SSD (`/Volumes/Ultra Touch/Broll-Masters`) | as needed | never in the cloud; fetched **on approval** by source id with `tools/fetch_masters.py` before a render |
| Shared library index | `library/index.json` in git | ~2 MB | facets (subjects / actions / setting / brand) for every owned clip; what 🔎 searches first |

## Rules
- **Never commit media.** `.gitignore` blocks `projects/*/previews/` and `projects/*/thumbs/`. All publishers and the bot write through `tools/release_media.py`.
- Asset names are `<scene>__<kind>__<file>` so a preview and its thumb can never collide. GitHub normalises names (runs of dots collapse to one) — always store the URL the API returns, never a constructed one.
- Uploads are serial with backoff. Parallel uploads trip GitHub's secondary rate limit.
- Masters are fetched, not stored: only approved clips ever get one, and only onto the SSD.

## Jobs
- `search-10-more.yml` — fires on a 🔎 / 🔁 click; ~90 s once the cached-ffmpeg step is in.
- `harvest.yml` — hourly Mon–Fri, stocks the shared library by every beat on every card so clicks promote off the shelf instead of hitting the internet. Budgeted per run; masters never stored.
- `tools/fetch_masters.py` — run on the Mac before rendering.

## Still to do
- Rewrite git history to drop the old 2.2 GB of blobs (deploys already ignore them; clones do not). Do this deliberately, with a backup, when nothing else is in flight.
