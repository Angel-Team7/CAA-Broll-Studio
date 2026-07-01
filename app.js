// Edenrise B-roll Cockpit — static dashboard.
// Approvals are held in memory + mirrored to localStorage. When a GitHub token
// is connected, Save/Send also commit selections/<slug>.json to the repo.

const $ = s => document.querySelector(s);
const state = { slug: null, data: null, approved: {}, reshoot: {} };
const gh = JSON.parse(localStorage.getItem("gh") || "null"); // {owner,repo,token,branch}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2600);
}

async function loadProjects() {
  const idx = await fetch("projects.json").then(r => r.json()).catch(() => null);
  const sel = $("#project");
  if (!idx || !idx.projects.length) { $("#scenes").innerHTML =
    '<p class="pad muted">No projects published yet. Run <code>publish_cockpit.py &lt;slug&gt;</code>.</p>'; return; }
  sel.innerHTML = idx.projects.map(p =>
    `<option value="${p.slug}">${p.title} — ${p.scenes} scenes</option>`).join("");
  sel.onchange = () => loadProject(sel.value);
  loadProject(idx.projects[0].slug);
}

async function loadProject(slug) {
  state.slug = slug;
  state.data = await fetch(`projects/${slug}/scenes.json`).then(r => r.json());
  const sel = await loadSelections(slug);
  state.approved = sel.approved || {};
  state.reshoot = sel.needs_broll || {};
  render();
}

// Prefer GitHub selections when connected, else localStorage. Returns the full
// selection object: { approved:{S01:[ids]}, needs_broll:{S01:"reason"} }.
async function loadSelections(slug) {
  if (gh && gh.token) {
    const got = await ghGet(`selections/${slug}.json`).catch(() => null);
    if (got) { try { return JSON.parse(atob(got.content)); } catch {} }
  }
  return JSON.parse(localStorage.getItem(`sel:${slug}`) || "{}");
}

function persistLocal() {
  localStorage.setItem(`sel:${state.slug}`,
    JSON.stringify({ approved: state.approved, needs_broll: state.reshoot }));
}

function render() {
  const d = state.data;
  const wrap = $("#scenes");
  wrap.innerHTML = d.scenes.map(sc => {
    const appr = state.approved[sc.id] || [];
    const flagged = sc.id in state.reshoot;
    const cards = sc.clips.map(c => card(sc.id, c, appr.includes(c.id))).join("");
    return `<section class="scene ${flagged ? "flagged" : ""}" data-scene="${sc.id}">
      <div class="scene-head">
        <span class="scene-id">${sc.id}</span>
        <div class="scene-meta">
          <div class="scene-dir">${esc(sc.visual_direction)}</div>
          <div class="scene-line">“${esc(sc.script_line)}”</div>
          ${flagged ? `<div class="reshoot-note">🔁 flagged for new footage${state.reshoot[sc.id] ? ' — “' + esc(state.reshoot[sc.id]) + '”' : ''}</div>` : ""}
        </div>
        <div class="scene-side">
          <div class="scene-count"><b class="c">${appr.length}</b> / ${sc.clips.length} approved</div>
          <button class="reshoot ${flagged ? "on" : ""}" data-scene="${sc.id}">${flagged ? "🔁 Flagged" : "🔁 Needs different"}</button>
        </div>
      </div>
      <div class="grid">${cards || '<p class="muted">No clips.</p>'}</div>
    </section>`;
  }).join("");
  wrap.querySelectorAll(".card").forEach(el =>
    el.onclick = e => { if (e.target.tagName !== "A") toggle(el); });
  wrap.querySelectorAll(".reshoot").forEach(el =>
    el.onclick = e => { e.stopPropagation(); toggleReshoot(el.dataset.scene); });
  wrap.querySelectorAll("video").forEach(v => {
    const p = v.closest(".media");
    p.onmouseenter = () => v.play().catch(()=>{});
    p.onmouseleave = () => { v.pause(); v.currentTime = 0; };
  });
  updateStat();
}

function card(sid, c, on) {
  const media = c.type === "video"
    ? `<video src="${c.preview}" muted loop playsinline preload="none" poster="${c.thumb}"></video>`
    : `<img src="${c.preview}" loading="lazy" alt="">`;
  const src = c.page_url ? `<a href="${c.page_url}" target="_blank" rel="noopener">${c.source}</a>` : c.source;
  return `<div class="card ${on ? "on" : ""} type-${c.type === "video" ? "vid" : "img"}"
      data-id="${c.id}" data-scene="${sid}">
    <div class="media"><span class="badge">${c.type}</span><span class="tick">✓</span>${media}</div>
    <div class="foot"><span>${src}</span><span class="lic">${esc(c.license || "")}</span></div>
  </div>`;
}

function toggle(el) {
  const sid = el.dataset.scene, id = el.dataset.id;
  const list = state.approved[sid] = state.approved[sid] || [];
  const i = list.indexOf(id);
  if (i >= 0) list.splice(i, 1); else list.push(id);
  if (!list.length) delete state.approved[sid];
  el.classList.toggle("on");
  const cnt = el.closest(".scene").querySelector(".scene-count .c");
  cnt.textContent = (state.approved[sid] || []).length;
  persistLocal();
  updateStat();
}

// Flag/unflag a scene as needing different B-roll (with an optional reason).
function toggleReshoot(sid) {
  if (sid in state.reshoot) {
    delete state.reshoot[sid];
  } else {
    const why = prompt(`What's wrong with ${sid}'s footage? (optional — e.g. "too office, want outdoor grounds crew")`, "");
    if (why === null) return;            // cancelled
    state.reshoot[sid] = why.trim();
  }
  persistLocal();
  render();
}

function updateStat() {
  const total = Object.values(state.approved).reduce((n, a) => n + a.length, 0);
  const scenes = state.data.scenes.length;
  const covered = state.data.scenes.filter(s => (state.approved[s.id] || []).length).length;
  const flags = Object.keys(state.reshoot).length;
  $("#stat").textContent = `${total} clips approved · ${covered}/${scenes} scenes covered` +
    (flags ? ` · ${flags} flagged 🔁` : "");
}

async function save(ready) {
  persistLocal();
  const payload = { project: state.slug, updated: new Date().toISOString(),
    ready: !!ready, approved: state.approved, needs_broll: state.reshoot };
  if (gh && gh.token) {
    try {
      await ghPut(`selections/${state.slug}.json`, JSON.stringify(payload, null, 2),
        ready ? "cockpit: send to editor" : "cockpit: save approvals");
      toast(ready ? "Sent to editor ▸ committed to GitHub" : "Saved to GitHub ✓");
    } catch (e) { toast("GitHub save failed: " + e.message); }
  } else {
    // local mode: also drop a downloadable file so the handoff script can read it
    downloadJSON(`${state.slug}.selection.json`, payload);
    toast(ready ? "Downloaded selection (ready) — no GitHub connected"
                : "Saved locally + downloaded selection.json");
  }
}

// ---- GitHub REST helpers (fine-grained token, contents:write on one repo) ----
function ghUrl(path) { return `https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${path}`; }
async function ghGet(path) {
  const r = await fetch(ghUrl(path) + `?ref=${gh.branch||"main"}`,
    { headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("GET " + r.status);
  return r.json();
}
async function ghPut(path, text, message) {
  const existing = await ghGet(path).catch(() => null);
  const body = { message, content: b64(text), branch: gh.branch || "main" };
  if (existing && existing.sha) body.sha = existing.sha;
  const r = await fetch(ghUrl(path), { method: "PUT",
    headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" },
    body: JSON.stringify(body) });
  if (!r.ok) throw new Error("PUT " + r.status);
  return r.json();
}

function connectGitHub() {
  const cur = gh || {};
  const owner = prompt("GitHub owner (user/org):", cur.owner || "edenrise");
  if (!owner) return;
  const repo = prompt("Repo name:", cur.repo || "edenrise-broll-cockpit");
  const branch = prompt("Branch:", cur.branch || "main") || "main";
  const token = prompt("Fine-grained token (contents:write on this repo). Stored in this browser only:");
  if (!token) return;
  localStorage.setItem("gh", JSON.stringify({ owner, repo, branch, token }));
  location.reload();
}

// ---- utils ----
const esc = s => (s || "").replace(/[&<>"]/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[m]));
const b64 = s => btoa(unescape(encodeURIComponent(s)));
function downloadJSON(name, obj) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }));
  a.download = name; a.click(); URL.revokeObjectURL(a.href);
}

$("#save").onclick = () => save(false);
$("#send").onclick = () => { if (confirm("Send the approved B-roll to the editor?")) save(true); };
$("#connect").onclick = connectGitHub;
if (gh && gh.token) { $("#savemode").textContent = `GitHub (${gh.owner}/${gh.repo})`; $("#connect").textContent = "Reconnect…"; }
loadProjects();
