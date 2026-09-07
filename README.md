# B-roll Cockpit — Edenrise & Belong

Static review dashboard for approving license-cleared B-roll per lesson.
Live at https://angel-team7.github.io/CAA-Broll-Studio/

## For reviewers (iPad, laptop, any browser)

1. Open the link, pick a lesson, hover or tap a clip to preview, tap the tick to approve.
2. Each scene shows **VIEWER HEARS** (the exact words the narrator says in that window, timed to
   the recorded audio when we have it, `≈` when estimated, or *narration not recorded yet*),
   **PICK FOOTAGE THAT SHOWS** (the visual brief), and the **ON-SCREEN TEXT**.
3. Ticks save themselves. The top bar shows `Saved ✓` / `Saving…` / `Not connected`.
   - **Connected** device: every tick is committed straight to the repo. Nothing to download.
   - **Not connected**: ticks stay in that browser only. Either tap **Connect GitHub…** and paste
     the access key Vic gives you (once per device), or press **Send to editor** to download the
     selections file and email it.
4. Two buttons per scene, both one click, no dialog:
   - **🔎 Need more** — 10 fresh clips of the *same* kind appear under the existing ones in ~2 min.
   - **🔁 Direction is wrong** — 10 clips of a *different* kind: the search deliberately avoids
     what is already on the card. Add a note first if you know what you want instead
     ("hands, not faces", "less office").
   Both run on GitHub's servers; nobody has to be at the Mac.

Approved ticks are never changed by automation. Only a human unticks.

## How it hangs together

| Piece | What it does | Details |
|---|---|---|
| Cards (`projects/<slug>/scenes.json`) | one card per lesson, one row per scene, with the spoken line, brief, timing and candidate clips | scripts arrive from Google Drive via the intake routine; timings come from the narration's `timing.json` when recorded |
| Approvals (`selections/<slug>.json`) | the client's ticks, notes, top-up and direction requests | written only by the cockpit UI |
| Previews & thumbs | 480p, on GitHub **Releases** (`media-<slug>`, `media-library`) | never in git — see `tools/README-media-architecture.md` |
| Masters | full resolution, on the SSD only | fetched per approved clip with `tools/fetch_masters.py` |
| Shared library (`library/index.json`) | every clip we own, faceted; searched first on every click | stocked hourly by the harvester |
| Search 10 more / Direction is wrong | GitHub Action fired by a click | `tools/README-search-10-more.md` |
| Script intake | Claude cloud routine, weekdays hourly: Drive → cards → commit | `tools/README-media-architecture.md` |

Slugs never change (approvals key on them). Titles may.
