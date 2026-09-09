#!/usr/bin/env python3
"""Media store for the cockpit: GitHub Releases, one per lesson.

Previews and thumbs never enter git. Each lesson has a release tagged
media-<slug>; assets are named <scene>__<kind>__<file> so an image's preview and
its thumbnail cannot collide. Uploads are serial with backoff — the secondary
rate limit punishes parallelism. Works locally (git credential) and in Actions
(GITHUB_TOKEN).
"""
import json, mimetypes, os, pathlib, subprocess, time
import requests

REPO = os.environ.get("COCKPIT_REPO", "Angel-Team7/CAA-Broll-Studio")
API = "https://api.github.com"

def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line[9:]
    raise RuntimeError("no GitHub token: set GH_TOKEN or store a git credential")

def _h():
    return {"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json"}

SHARD_AT = 990          # GitHub refuses the 1,001st asset on a release (422 file_count)
_shard_cache = {}


class ReleaseFull(Exception):
    pass


def _release_by_tag(tag):
    r = requests.get(f"{API}/repos/{REPO}/releases/tags/{tag}", headers=_h(), timeout=60)
    return r.json() if r.status_code == 200 else None


def _create_release(tag, slug):
    r = requests.post(f"{API}/repos/{REPO}/releases", headers=_h(), timeout=60, json={
        "tag_name": tag, "name": f"Media — {slug}" + ("" if tag == f"media-{slug}" else f" ({tag.rsplit('-', 1)[-1]})"),
        "body": f"480p previews, thumbnails and judge strips for the {slug} cockpit card. "
                "Kept out of git so Pages deploys stay small. Releases are sharded at 1,000 assets."})
    r.raise_for_status()
    return r.json()


def ensure_release(slug, fresh=False):
    """The first release for this slug that still has room. GitHub caps a release at
    1,000 assets, so media-<slug>, media-<slug>-2, media-<slug>-3 … are one store."""
    if not fresh and slug in _shard_cache:
        return _shard_cache[slug]
    n = 1
    while True:
        tag = f"media-{slug}" if n == 1 else f"media-{slug}-{n}"
        rel = _release_by_tag(tag)
        if rel is None:
            rel = _create_release(tag, slug)
        if len(rel.get("assets") or []) < SHARD_AT:
            _shard_cache[slug] = (tag, rel["id"])
            return _shard_cache[slug]
        n += 1


def upload_for_slug(slug, name, path):
    """Upload into whichever shard has room; roll to the next shard when one fills mid-run."""
    for attempt in range(2):
        tag, rel_id = ensure_release(slug, fresh=(attempt > 0))
        try:
            return upload(rel_id, name, path)
        except ReleaseFull:
            _shard_cache.pop(slug, None)
    return None

def existing(rel_id):
    names, page = set(), 1
    while True:
        r = requests.get(f"{API}/repos/{REPO}/releases/{rel_id}/assets", headers=_h(),
                         params={"per_page": 100, "page": page}, timeout=60).json()
        if not r:
            return names
        names |= {a["name"] for a in r}
        page += 1

def asset_name(scene_id, kind, path):
    return f"{scene_id}__{kind}__{pathlib.Path(path).name}"

def asset_urls(rel_id):
    """name -> browser_download_url, keyed by the name GitHub actually assigned."""
    out, page = {}, 1
    while True:
        r = requests.get(f"{API}/repos/{REPO}/releases/{rel_id}/assets", headers=_h(),
                         params={"per_page": 100, "page": page}, timeout=60).json()
        if not r:
            return out
        for a in r:
            out[a["name"]] = a["browser_download_url"]
        page += 1

def upload(rel_id, name, path, tries=6):
    """Upload one asset; return the URL GitHub serves it from, or None.

    GitHub rewrites characters it dislikes in asset names, and a constructed URL
    with a '?' or ',' in it 404s — so the returned URL is the only safe one.
    Uploads are serial; a 403/429 is the secondary rate limit and is waited out
    (Retry-After when given, else a minute), never hammered.
    """
    ct = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = pathlib.Path(path).read_bytes()
    last = ""
    for i in range(tries):
        try:
            r = requests.post(f"https://uploads.github.com/repos/{REPO}/releases/{rel_id}/assets",
                              headers={**_h(), "Content-Type": ct}, params={"name": name},
                              data=data, timeout=300)
        except Exception as e:
            last = f"network: {str(e)[:80]}"; time.sleep(10 * (i + 1)); continue
        if r.status_code == 201:
            time.sleep(0.8)                   # be a polite serial uploader
            return r.json()["browser_download_url"]
        if r.status_code == 422 and "file_count" in r.text:
            raise ReleaseFull(name)
        if r.status_code == 422:               # already there — look it up
            urls = asset_urls(rel_id)
            import re
            key = re.sub(r"[^A-Za-z0-9._-]", ".", name)
            for n, u in urls.items():
                if re.sub(r"[^A-Za-z0-9._-]", ".", n) == key:
                    return u
            last = "422 but no matching asset"; break
        last = f"{r.status_code} {r.text[:120]}"
        if r.status_code in (403, 429):
            wait = int(r.headers.get("Retry-After") or 0) or 60
            print(f"    upload rate-limited ({name}) — waiting {wait}s"); time.sleep(wait)
        else:
            time.sleep((i + 1) * 15)
    print(f"    upload failed ({name}): {last}")
    return None

def rewrite_scenes(slug, cock_root, scenes, keep_local=True):
    """Upload every local preview/thumb referenced in `scenes`, swap paths for URLs.

    Local copies are kept as a mirror (they are gitignored). Returns the scenes.
    """
    cock_root = pathlib.Path(cock_root)
    tag, rel_id = ensure_release(slug)
    have = asset_urls(rel_id)
    n_up = n_skip = 0
    for sc in scenes:
        for c in sc.get("clips", []):
            for kind in ("preview", "thumb"):
                p = c.get(kind)
                if not p or str(p).startswith("http"):
                    continue
                local = cock_root / p
                if not local.exists():
                    continue
                name = asset_name(sc["id"], kind, p)
                url = have.get(name)
                if url:
                    n_skip += 1
                else:
                    url = upload(rel_id, name, local)
                    if not url:
                        print(f"  ! upload failed, leaving local path: {name}")
                        continue
                    have[name] = url; n_up += 1
                c[kind] = url
                if not keep_local:
                    local.unlink(missing_ok=True)
    print(f"  release {tag}: {n_up} uploaded, {n_skip} already there")
    return scenes
