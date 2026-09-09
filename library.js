// Edenrise B-roll Library — a cross-linked wiki over library/index.json.
//
// The cockpit answers "what goes in THIS scene". This answers "what do we own",
// which is a different question and needs a different shape: every clip is a page,
// every facet value is a page, and both link to each other. Nothing here edits a
// card — curation (★, tags, notes) lives in its own file, library/curation.json.

const $ = s => document.querySelector(s);
const gh = JSON.parse(localStorage.getItem("gh") || "null");   // set by the cockpit's Connect dialog
const S = { assets: [], byKey: new Map(), idx: {}, cur: { clips: {} },
            mediaProxy: "", titles: {}, shown: 0, rows: [] };

const PAGE = 120;                                  // tiles rendered before "show more"
const RELEASE_BASE = "https://github.com/Angel-Team7/CAA-Broll-Studio/releases/download/";

// Facets a B-roll director actually files by. `multi` = the asset can carry several.
const FACETS = [
  { id: "subjects", label: "Who is on screen", multi: true,  icon: "🧍" },
  { id: "actions",  label: "What they are doing", multi: true, icon: "🔨" },
  { id: "setting",  label: "Where it happens", multi: true,  icon: "📍" },
  { id: "theme",    label: "Harvest theme",   multi: false, icon: "🎯" },
  { id: "curated",  label: "Editor tags",     multi: true,  icon: "🏷️" },
  { id: "brand",    label: "World",           multi: false, icon: "🌍" },
  { id: "scale",    label: "Shot scale",      multi: false, icon: "🔍" },
  { id: "people",   label: "People in shot",  multi: false, icon: "👥" },
  { id: "source",   label: "Source",          multi: false, icon: "📦" },
  { id: "status",   label: "Spent or shelf",  multi: false, icon: "📊" },
  { id: "tags",     label: "Free tags",       multi: true,  icon: "#️⃣" },
];
const FACET = Object.fromEntries(FACETS.map(f => [f.id, f]));

// Every facet reads off the asset the same way, so one function drives the index,
// the chips, the related-clip scoring and the search.
function valuesOf(a, facet) {
  switch (facet) {
    case "curated": return (S.cur.clips[a.key] || {}).tags || [];
    case "status":  return [a.dead ? "dead link"
                          : !a.used_in.length ? "on the shelf"
                          : a.used_in.length > 1 ? "reused" : "spent once"];
    case "theme":   return a.theme ? [a.theme] : [];
    default: {
      const v = a[facet];
      return v == null ? [] : Array.isArray(v) ? v : [v];
    }
  }
}

// ---------- load ----------
async function boot() {
  const bust = "?v=" + Date.now();
  const [lib, projects, cur] = await Promise.all([
    fetch("library/index.json" + bust, { cache: "no-store" }).then(r => r.json()),
    fetch("projects.json" + bust, { cache: "no-store" }).then(r => r.json()).catch(() => null),
    loadCuration(),
  ]);
  S.assets = lib.assets || [];
  S.assets.forEach(a => S.byKey.set(a.key, a));
  S.cur = cur;
  S.mediaProxy = ((projects || {}).media_proxy || "").trim();
  ((projects || {}).projects || []).forEach(p => { S.titles[p.slug] = p.title; });
  buildIndex();
  refreshConnBanner();
  window.addEventListener("hashchange", route);
  $("#q").addEventListener("input", e => {
    const v = e.target.value.trim();
    clearTimeout(boot._t);
    boot._t = setTimeout(() => { location.hash = v ? "#/q/" + encodeURIComponent(v) : "#/"; }, 250);
  });
  route();
}

// value -> assets, per facet. Rebuilt when editor tags change so the wiki links stay true.
function buildIndex() {
  S.idx = {};
  for (const f of FACETS) {
    const m = new Map();
    for (const a of S.assets)
      for (const v of valuesOf(a, f.id)) {
        if (!m.has(v)) m.set(v, []);
        m.get(v).push(a);
      }
    S.idx[f.id] = m;
  }
}

// ---------- curation (its own file — never selections/, never a scene's clips) ----------
async function loadCuration() {
  if (gh && gh.token) {
    const got = await ghGet("library/curation.json").catch(() => null);
    if (got) { try { return norm(JSON.parse(decodeURIComponent(escape(atob(got.content))))); } catch {} }
  }
  try { return norm(JSON.parse(localStorage.getItem("libcur") || "{}")); } catch { return norm({}); }
}
const norm = o => ({ clips: (o && o.clips) || {} });

function entry(key) {
  return S.cur.clips[key] || (S.cur.clips[key] = { star: false, tags: [], note: "" });
}
let saveTimer = null;
function saveCuration() {
  // Opening a clip page materialises an entry; only keep the ones that say something,
  // or the file fills up with empty rows for every clip anyone ever looked at.
  for (const [k, v] of Object.entries(S.cur.clips))
    if (!v.star && !v.tags.length && !v.note) delete S.cur.clips[k];
  localStorage.setItem("libcur", JSON.stringify(S.cur));
  buildIndex();
  if (!(gh && gh.token)) return;
  clearTimeout(saveTimer);
  setSync("saving");
  saveTimer = setTimeout(async () => {
    try {
      await ghPut("library/curation.json",
        JSON.stringify({ updated: new Date().toISOString(), clips: S.cur.clips }, null, 2),
        "library: curation update");
      setSync("saved");
    } catch (e) { setSync("error"); toast("Could not save to GitHub: " + e.message); }
  }, 1500);
}
function setSync(k) {
  const el = $("#syncstate");
  el.textContent = { saving: "saving…", saved: "curation saved ✓", error: "save failed" }[k] || "";
  el.className = "syncstate " + k;
}
function refreshConnBanner() {
  $("#localwarn").hidden = !!(gh && gh.token);
  if (gh && gh.token) $("#savemode").textContent = `GitHub (${gh.owner}/${gh.repo})`;
}

// ---------- routing ----------
function route() {
  const parts = (location.hash.slice(1) || "/").split("/").filter(Boolean).map(decodeURIComponent);
  S.shown = PAGE;
  window.scrollTo(0, 0);
  const stars = S.assets.filter(a => (S.cur.clips[a.key] || {}).star).length;
  $("#stat").textContent = `${S.assets.length.toLocaleString()} clips${stars ? ` · ${stars} ★` : ""}`;
  if (parts[0] !== "q") $("#q").value = "";
  const view = $("#view");
  if (!parts.length)                 return home(view);
  if (parts[0] === "f")              return facetPage(view, parts[1], parts.slice(2).join("/"));
  if (parts[0] === "clip")           return clipPage(view, parts.slice(1).join("/"));
  if (parts[0] === "lesson")         return lessonPage(view, parts[1]);
  if (parts[0] === "starred")        return listPage(view, "★ Benchmarks",
                                        "The clips the team marked as the best of their kind.",
                                        S.assets.filter(a => (S.cur.clips[a.key] || {}).star));
  if (parts[0] === "q")              return searchPage(view, parts.slice(1).join("/"));
  home(view);
}

function crumbs(trail) {
  $("#crumbs").innerHTML = ['<a href="#/">Archive</a>']
    .concat(trail.map(t => `<span class="sep">›</span>${esc(t)}`)).join("");
}

// ---------- pages ----------
function home(view) {
  crumbs([]);
  const stars = S.assets.filter(a => (S.cur.clips[a.key] || {}).star);
  const shelf = S.assets.filter(a => !a.used_in.length)
    .sort((a, b) => String(b.harvested || "").localeCompare(String(a.harvested || "")));
  const reused = S.assets.filter(a => a.used_in.length > 1)
    .sort((a, b) => b.used_in.length - a.used_in.length);
  const vids = S.assets.filter(a => a.type === "video").length;

  view.innerHTML = `
    <section class="hero">
      <h2>Everything we own, filed by what it shows</h2>
      <p class="muted">Every clip the harvester has ever gathered, on one shelf: what it is,
      what it shows, where it came from, what it is licensed as, and which lessons have
      already spent it. Follow any tag to everything else that carries it.</p>
      <div class="statrow">
        ${stat(S.assets.length, "clips")}${stat(vids, "video")}${stat(S.assets.length - vids, "stills")}
        ${stat(shelf.length, "unspent")}${stat(reused.length, "reused")}
        ${stat(stars.length, "★ benchmarks", "#/starred")}
      </div>
    </section>
    ${stars.length ? shelfRow("★ Benchmarks", "The best of their kind, picked by the team.", stars, "#/starred") : ""}
    ${shelfRow("🌱 On the shelf", "Harvested, never used on a card yet — freshest first.", shelf, "#/f/status/" + encodeURIComponent("on the shelf"))}
    ${shelfRow("♻️ Most reused", "Footage that keeps earning its place.", reused, "#/f/status/reused")}
    <h3 class="secttl">Browse by facet</h3>
    <div class="facets">${FACETS.map(facetCard).join("")}</div>
    <h3 class="secttl">Lessons</h3>
    <div class="chips">${lessonChips(S.assets)}</div>`;
  wireTiles(view);
}

const stat = (n, label, href) => {
  const inner = `<b>${n.toLocaleString()}</b><span>${label}</span>`;
  return href ? `<a class="statbox" href="${href}">${inner}</a>` : `<div class="statbox">${inner}</div>`;
};

function shelfRow(title, sub, assets, href) {
  if (!assets.length) return "";
  return `<section class="shelf">
    <div class="shelfhead"><h3>${title}</h3><span class="muted">${esc(sub)}</span>
      <a class="more" href="${href}">all ${assets.length} ▸</a></div>
    <div class="strip">${assets.slice(0, 12).map(tile).join("")}</div>
  </section>`;
}

function facetCard(f) {
  const m = S.idx[f.id];
  const vals = [...m.entries()].sort((a, b) => b[1].length - a[1].length);
  if (!vals.length) return "";
  const top = vals.slice(0, f.id === "tags" ? 30 : 24);
  return `<section class="facetcard">
    <h4>${f.icon} ${esc(f.label)} <span class="muted">${vals.length}</span></h4>
    <div class="chips">${top.map(([v, list]) => chip(f.id, v, list.length)).join("")}</div>
    ${vals.length > top.length ? `<p class="muted small">+ ${vals.length - top.length} more</p>` : ""}
  </section>`;
}

const chip = (facet, value, n) =>
  `<a class="chip" href="#/f/${encodeURIComponent(facet)}/${encodeURIComponent(value)}"
      title="${esc(FACET[facet] ? FACET[facet].label : facet)}">${esc(clip50(value))}<span>${n}</span></a>`;

const clip50 = v => String(v).length > 52 ? String(v).slice(0, 50) + "…" : String(v);

// fix_library_urls.py marks the rows whose media no longer resolves anywhere. Their
// preview field still holds the old projects/… path, so rendering it would give the
// editor a broken tile instead of the truth.
const playable = a => String(a.preview || "").startsWith("http") && !a.dead;
const posterOf = a => {
  const u = a.thumb || a.preview || "";
  return String(u).startsWith("http") ? mediaUrl(u) : "";
};

// Most rows carry a title, or the search that found them. The rest can borrow the
// descriptive slug the stock site already put in its own URL — anything rather than
// showing an editor the raw key.
function label(a) {
  if (a.title) return a.title;
  if (a.query) return a.query;
  if (a.theme) return a.theme;
  const seg = (a.page_url || "").replace(/[/?#]+$/, "").split("/").pop() || "";
  const words = decodeURIComponent(seg).replace(/[-_]+/g, " ").replace(/\b\d{4,}\b/g, "").trim();
  return words.length > 2 ? words : `${a.source}${a.src_id ? " #" + a.src_id : ""}`;
}

function lessonChips(assets) {
  const m = new Map();
  for (const a of assets)
    for (const u of a.used_in) m.set(u.project, (m.get(u.project) || 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([slug, n]) =>
    `<a class="chip" href="#/lesson/${encodeURIComponent(slug)}">${esc(S.titles[slug] || slug)}<span>${n}</span></a>`
  ).join("") || '<p class="muted">Nothing spent yet.</p>';
}

function facetPage(view, facet, value) {
  const list = (S.idx[facet] || new Map()).get(value) || [];
  const f = FACET[facet] || { label: facet, icon: "🏷️" };
  crumbs([f.label, value]);
  if (!list.length) {
    view.innerHTML = `<p class="pad muted">Nothing filed under <b>${esc(value)}</b>.
      <a href="#/">Back to the archive</a>.</p>`;
    return;
  }
  view.innerHTML = `
    <section class="pagehead">
      <div class="kicker">${f.icon} ${esc(f.label)}</div>
      <h2>${esc(value)}</h2>
      <p class="muted">${list.length} clip${list.length === 1 ? "" : "s"} carry this
        · ${list.filter(a => a.type === "video").length} video
        · ${list.filter(a => !a.used_in.length).length} still unspent</p>
      ${related(list, facet, value)}
      <div class="alsoblock"><b class="alsottl">Spent on</b>
        <div class="chips">${lessonChips(list)}</div></div>
    </section>
    ${gridSection(list)}`;
  wireTiles(view);
}

// The cross-links that make this a wiki rather than a filter: what else do the clips
// under this heading have in common? Ranked by how much of the subset shares it.
function related(list, facet, value) {
  const out = [];
  for (const f of FACETS) {
    if (f.id === facet || f.id === "tags") continue;
    const m = new Map();
    for (const a of list)
      for (const v of valuesOf(a, f.id)) m.set(v, (m.get(v) || 0) + 1);
    for (const [v, n] of m)
      if (n >= 2 && n < list.length) out.push({ facet: f.id, v, n });
  }
  out.sort((a, b) => b.n - a.n);
  const top = out.slice(0, 16);
  if (!top.length) return "";
  return `<div class="alsoblock"><b class="alsottl">Also tagged</b>
    <div class="chips">${top.map(o => chip(o.facet, o.v, o.n)).join("")}</div></div>`;
}

function clipPage(view, key) {
  const a = S.byKey.get(key);
  if (!a) { view.innerHTML = `<p class="pad muted">No clip with that id. <a href="#/">Back</a>.</p>`; return; }
  const c = entry(a.key);
  crumbs([clip50(label(a))]);
  const isVid = a.type === "video";
  const poster = posterOf(a);
  const media = !playable(a)
    ? `<div class="media big"><span class="badge">${isVid ? "video" : "still"}</span>
         <span class="nopreview">media gone — the source page still works, the copy we held does not</span></div>`
    : isVid
    ? `<div class="media big" data-preview="${esc(mediaUrl(a.preview))}">
         <span class="badge">video</span>${poster ? `<img class="poster" src="${esc(poster)}" alt="">` : ""}</div>`
    : `<div class="media big"><span class="badge">still</span><img src="${esc(mediaUrl(a.preview))}" alt=""></div>`;

  const rows = [
    ["Source", a.page_url ? `<a href="${esc(a.page_url)}" target="_blank" rel="noopener">${esc(a.source)} ↗</a>` : esc(a.source)],
    ["Author", esc(a.author || "—")],
    ["Licence", esc(a.license || "—")],
    ["Search that found it", esc(a.query || "—")],
    ["Harvested", esc((a.harvested || "").slice(0, 10) || "—")],
  ];

  view.innerHTML = `
    <section class="cliphead">
      ${media}
      <div class="clipmeta">
        <h2>${esc(label(a))}</h2>
        <div class="chips">${FACETS.filter(f => f.id !== "tags").flatMap(f =>
            valuesOf(a, f.id).map(v => chip(f.id, v, (S.idx[f.id].get(v) || []).length))).join("")}</div>
        <table class="meta">${rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}</table>
        <div class="curate">
          <button id="star" class="starbtn ${c.star ? "on" : ""}">${c.star ? "★ Benchmark" : "☆ Mark as benchmark"}</button>
          <label class="cfield">Editor tags <span class="muted">comma separated — these become wiki pages too</span>
            <input id="ctags" value="${esc(c.tags.join(", "))}" placeholder="hero shot, opening, golden hour"></label>
          <label class="cfield">Note for the edit
            <textarea id="cnote" rows="2" placeholder="Why this one — and what it is good for.">${esc(c.note)}</textarea></label>
        </div>
        ${a.used_in.length ? `<div class="alsoblock"><b class="alsottl">Already spent on</b><ul class="usedlist">${
          a.used_in.map(u => `<li><a href="#/lesson/${encodeURIComponent(u.project)}">${esc(S.titles[u.project] || u.project)}</a>
            <span class="muted">scene ${esc(u.scene)}</span>
            <a class="cockpitjump" href="index.html?p=${encodeURIComponent(u.project)}" title="Open this lesson in the cockpit">open card ▸</a></li>`).join("")}</ul></div>`
          : `<p class="shelfnote">🌱 On the shelf — no lesson has used this yet.</p>`}
        ${a.tags.length ? `<div class="alsoblock"><b class="alsottl">Free tags</b><div class="chips">${
          a.tags.map(t => chip("tags", t, (S.idx.tags.get(t) || []).length)).join("")}</div></div>` : ""}
      </div>
    </section>
    <h3 class="secttl">Footage like this</h3>
    ${gridSection(relatedClips(a))}`;

  $("#star").onclick = () => {
    c.star = !c.star;
    $("#star").classList.toggle("on", c.star);
    $("#star").textContent = c.star ? "★ Benchmark" : "☆ Mark as benchmark";
    saveCuration();
    toast(c.star ? "Marked as a benchmark ★" : "Benchmark removed");
  };
  $("#ctags").onchange = e => {
    c.tags = e.target.value.split(",").map(s => s.trim()).filter(Boolean);
    saveCuration(); route();
  };
  $("#cnote").onchange = e => { c.note = e.target.value.trim(); saveCuration(); };
  wireTiles(view);
}

// Shared facet values, weighted: a theme match says far more than "both outdoors".
const WEIGHT = { theme: 6, curated: 5, actions: 3, subjects: 2, setting: 2, scale: 1, people: 1, tags: 1 };
function relatedClips(a) {
  const mine = {};
  for (const f of Object.keys(WEIGHT)) mine[f] = new Set(valuesOf(a, f));
  return S.assets.map(b => {
    if (b.key === a.key) return null;
    let score = 0;
    for (const f of Object.keys(WEIGHT))
      for (const v of valuesOf(b, f)) if (mine[f].has(v)) score += WEIGHT[f];
    return score >= 4 ? { b, score } : null;
  }).filter(Boolean).sort((x, y) => y.score - x.score).slice(0, 24).map(x => x.b);
}

function lessonPage(view, slug) {
  const list = S.assets.filter(a => a.used_in.some(u => u.project === slug));
  crumbs([S.titles[slug] || slug]);
  const byScene = new Map();
  for (const a of list)
    for (const u of a.used_in)
      if (u.project === slug) {
        if (!byScene.has(u.scene)) byScene.set(u.scene, []);
        byScene.get(u.scene).push(a);
      }
  const scenes = [...byScene.entries()].sort((x, y) =>
    (parseInt(x[0].replace(/\D/g, ""), 10) || 0) - (parseInt(y[0].replace(/\D/g, ""), 10) || 0));
  view.innerHTML = `
    <section class="pagehead">
      <div class="kicker">🎬 Lesson</div>
      <h2>${esc(S.titles[slug] || slug)}</h2>
      <p class="muted">${list.length} library clips across ${scenes.length} scenes.
        <a class="cockpitjump" href="index.html?p=${encodeURIComponent(slug)}">open this card in the cockpit ▸</a></p>
      ${related(list, "none", "")}
    </section>
    ${scenes.map(([sid, as]) => `<section class="shelf">
        <div class="shelfhead"><h3>${esc(sid)}</h3><span class="muted">${as.length} clips</span></div>
        <div class="strip">${as.map(tile).join("")}</div></section>`).join("")}`;
  wireTiles(view);
}

function searchPage(view, q) {
  $("#q").value = q;
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  // page_url carries the stock site's own descriptive slug, which is often the only
  // words a bare row has — searching it makes those clips findable at all.
  const hay = a => [a.title, a.query, a.author, a.source, a.theme, a.brand, a.scale, a.people,
                    (a.page_url || "").replace(/[-_/]+/g, " "),
                    ...(a.subjects || []), ...(a.actions || []), ...(a.setting || []),
                    ...(a.tags || []), ...valuesOf(a, "curated")].join(" ").toLowerCase();
  const hits = S.assets.filter(a => { const h = hay(a); return terms.every(t => h.includes(t)); });
  listPage(view, `“${q}”`, `${hits.length} clip${hits.length === 1 ? "" : "s"} match every word.`, hits, [q]);
}

function listPage(view, title, sub, list, trail) {
  crumbs(trail || [title]);
  view.innerHTML = `
    <section class="pagehead"><h2>${esc(title)}</h2><p class="muted">${esc(sub)}</p>
      ${list.length ? related(list, "none", "") : ""}</section>
    ${list.length ? gridSection(list) : '<p class="pad muted">Nothing matched.</p>'}`;
  wireTiles(view);
}

// ---------- tiles ----------
function gridSection(list) {
  S.rows = list;
  return `<div class="grid" id="grid">${list.slice(0, S.shown).map(tile).join("")}</div>
    ${list.length > S.shown ? `<div class="morewrap"><button id="more">Show ${
      Math.min(PAGE, list.length - S.shown)} more of ${list.length}</button></div>` : ""}`;
}

function tile(a) {
  const c = S.cur.clips[a.key] || {};
  const poster = posterOf(a);
  return `<a class="card" href="#/clip/${encodeURIComponent(a.key)}">
    <div class="media"${a.type === "video" && playable(a) ? ` data-preview="${esc(mediaUrl(a.preview))}"` : ""}>
      <span class="badge">${a.type === "video" ? "video" : "still"}</span>
      ${c.star ? '<span class="starflag">★</span>' : ""}
      ${a.dead ? '<span class="deadflag">dead link</span>'
        : !a.used_in.length ? '<span class="shelfflag">shelf</span>' : ""}
      ${poster ? `<img class="poster" src="${esc(poster)}" loading="lazy" alt="">`
        : `<span class="nopreview">${a.dead ? "media gone" : "no preview"}</span>`}
    </div>
    <div class="tfoot"><span class="ttl" title="${esc(label(a))}">${esc(clip50(label(a)))}</span>
      <span class="muted">${esc(a.source)}</span></div>
  </a>`;
}

function wireTiles(view) {
  view.querySelectorAll(".media[data-preview]").forEach(wirePreview);
  const more = view.querySelector("#more");
  if (more) more.onclick = () => {
    S.shown += PAGE;
    const grid = view.querySelector("#grid");
    grid.insertAdjacentHTML("beforeend", S.rows.slice(S.shown - PAGE, S.shown).map(tile).join(""));
    more.parentElement.outerHTML = S.rows.length > S.shown
      ? `<div class="morewrap"><button id="more">Show ${Math.min(PAGE, S.rows.length - S.shown)} more of ${S.rows.length}</button></div>` : "";
    wireTiles(view);
  };
}

// A grid can hold hundreds of clips; a <video> per tile is what turns Safari black.
// Same rule as the cockpit: poster until hovered, player built then, torn down after.
function wirePreview(m) {
  if (m.dataset.wired) return;
  m.dataset.wired = "1";
  const btn = document.createElement("button");
  btn.className = "playbtn"; btn.type = "button"; btn.textContent = "▶"; btn.title = "Play preview";
  btn.onclick = e => { e.preventDefault(); e.stopPropagation();
    m.classList.contains("playing") ? stopPreview(m) : startPreview(m); };
  m.appendChild(btn);
  m.addEventListener("pointerenter", e => { if (e.pointerType !== "touch") startPreview(m); });
  m.addEventListener("pointerleave", e => { if (e.pointerType !== "touch") stopPreview(m); });
}
async function startPreview(m) {
  let v = m.querySelector("video");
  if (!v) {
    v = document.createElement("video");
    v.src = m.dataset.preview; v.muted = true; v.loop = true; v.playsInline = true; v.preload = "auto";
    const p = m.querySelector("img.poster"); if (p) v.poster = p.src;
    m.insertBefore(v, m.querySelector(".playbtn"));
  }
  m.classList.add("loading");
  try { v._play = v.play(); await v._play; m.classList.add("playing"); }
  catch (e) { if (e && e.name !== "AbortError") toast("Preview could not start: " + e.message); }
  finally { m.classList.remove("loading"); }
}
function stopPreview(m) {
  const v = m.querySelector("video");
  if (!v) return;
  (v._play || Promise.resolve()).catch(() => {}).then(() => {
    v.pause(); v.removeAttribute("src"); try { v.load(); } catch {}
    v.remove(); m.classList.remove("playing", "loading");
  });
}

// ---------- GitHub + utils (same contract as app.js) ----------
function ghUrl(p) { return `https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${p}`; }
async function ghGet(path) {
  const r = await fetch(ghUrl(path) + `?ref=${gh.branch || "main"}&_=${Date.now()}`,
    { cache: "no-store", headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("GET " + r.status);
  return r.json();
}
async function ghPut(path, text, message) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const existing = await ghGet(path).catch(() => null);
    const body = { message, content: b64(text), branch: gh.branch || "main" };
    if (existing && existing.sha) body.sha = existing.sha;
    const r = await fetch(ghUrl(path), { method: "PUT",
      headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" },
      body: JSON.stringify(body) });
    if (r.ok) return r.json();
    if (r.status === 409 && attempt < 3) { await new Promise(res => setTimeout(res, 500)); continue; }
    throw new Error("PUT " + r.status);
  }
}

function mediaUrl(u) {
  if (!u || !S.mediaProxy || !u.startsWith(RELEASE_BASE)) return u || "";
  return S.mediaProxy.replace(/\/+$/, "") + "/" + u.slice(RELEASE_BASE.length);
}
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const b64 = s => btoa(unescape(encodeURIComponent(s)));
function toast(msg, ms) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms || 2600);
}

boot().catch(e => { $("#view").innerHTML = `<p class="pad muted">Could not load the archive: ${esc(e.message)}</p>`; });
