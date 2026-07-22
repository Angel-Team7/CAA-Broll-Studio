// Edenrise B-roll Cockpit — static dashboard.
// Approvals are held in memory + mirrored to localStorage. When a GitHub token
// is connected, Save/Send also commit selections/<slug>.json to the repo.

const $ = s => document.querySelector(s);
const state = { slug: null, data: null, approved: {}, reshoot: {}, finalised: [], projects: [] };
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
  state.projects = idx.projects;
  state.finalised = await loadFinalised();
  renderProjectSelect();
  renderProgress();
  sel.onchange = () => loadProject(sel.value);
  loadProject(idx.projects[0].slug);
}

function renderProjectSelect() {
  const sel = $("#project"); const cur = sel.value;
  sel.innerHTML = state.projects.map(p =>
    `<option value="${p.slug}">${state.finalised.includes(p.slug) ? "✅ " : "◻︎ "}${p.title} — ${p.scenes} scenes</option>`).join("");
  if (cur) sel.value = cur;
}

// ---- Finalised tracking (shared list in the repo, like selections) ----
async function loadFinalised() {
  if (gh && gh.token) {
    const got = await ghGet("finalised.json").catch(() => null);
    if (got) { try { return JSON.parse(atob(got.content)).finalised || []; } catch {} }
  }
  return JSON.parse(localStorage.getItem("finalised") || "[]");
}
async function saveFinalised() {
  localStorage.setItem("finalised", JSON.stringify(state.finalised));
  if (gh && gh.token) {
    try { await ghPut("finalised.json", JSON.stringify({ finalised: state.finalised }, null, 2), "cockpit: update finalised list"); }
    catch (e) { toast("GitHub save failed: " + e.message); }
  }
}
function renderProgress() {
  const total = state.projects.length, done = state.finalised.filter(s => state.projects.some(p => p.slug === s)).length;
  const remaining = state.projects.filter(p => !state.finalised.includes(p.slug)).map(p => p.title);
  $("#progressbar").innerHTML = `<b class="pdone">${done}/${total} finalised</b>` +
    (remaining.length ? ` &nbsp;·&nbsp; <span class="muted">remaining: ${remaining.map(esc).join(" · ")}</span>`
                      : ` &nbsp;·&nbsp; <span class="pdone">all lessons finalised 🎉</span>`);
}
function updateFinaliseBtn() {
  const on = state.finalised.includes(state.slug);
  const b = $("#finalise"); if (!b) return;
  b.textContent = on ? "✅ Finalised" : "✓ Mark finalised"; b.classList.toggle("on", on);
}
async function toggleFinalise() {
  const i = state.finalised.indexOf(state.slug);
  if (i >= 0) state.finalised.splice(i, 1); else state.finalised.push(state.slug);
  updateFinaliseBtn(); renderProjectSelect(); renderProgress();
  await saveFinalised();
  toast(state.finalised.includes(state.slug) ? "Marked finalised ✅" : "Unmarked");
}

async function loadProject(slug) {
  state.slug = slug;
  state.data = await fetch(`projects/${slug}/scenes.json`).then(r => r.json());
  const sel = await loadSelections(slug);
  state.approved = sel.approved || {};
  state.reshoot = sel.needs_broll || {};
  render();
  updateFinaliseBtn();
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
          <button class="addbroll" data-scene="${sc.id}" title="Upload a video or image — or drag &amp; drop files here">＋ Add B-roll</button>
          <div class="drophint">or drag &amp; drop files here</div>
        </div>
      </div>
      <div class="grid">${cards || '<p class="muted">No clips.</p>'}</div>
    </section>`;
  }).join("");
  wrap.querySelectorAll(".card").forEach(el =>
    el.onclick = e => { if (e.target.tagName !== "A") toggle(el); });
  wrap.querySelectorAll(".reshoot").forEach(el =>
    el.onclick = e => { e.stopPropagation(); toggleReshoot(el.dataset.scene); });
  wrap.querySelectorAll(".addbroll").forEach(el =>
    el.onclick = e => { e.stopPropagation(); startUpload(el.dataset.scene); });
  wireDropZones(wrap);
  wrap.querySelectorAll("video").forEach(v => {
    const p = v.closest(".media");
    p.onmouseenter = () => v.play().catch(()=>{});
    p.onmouseleave = () => { v.pause(); v.currentTime = 0; };
  });
  updateStat();
}

const SRC_LABEL = { heygen: "HeyGen", upload: "Uploaded" };
function card(sid, c, on) {
  const media = c.type === "video"
    ? `<video src="${c.preview}" muted loop playsinline preload="none" poster="${c.thumb || ""}"></video>`
    : `<img src="${c.preview}" loading="lazy" alt="">`;
  const src = c.page_url ? `<a href="${c.page_url}" target="_blank" rel="noopener">${esc(c.source)}</a>` : esc(c.source);
  const srcTag = SRC_LABEL[c.source]
    ? `<span class="srcbadge src-${c.source}">${SRC_LABEL[c.source]}</span>` : "";
  const note = c.note ? `<div class="clip-note">${esc(c.note)}</div>` : "";
  return `<div class="card ${on ? "on" : ""} type-${c.type === "video" ? "vid" : "img"}"
      data-id="${c.id}" data-scene="${sid}">
    <div class="media"><span class="badge">${c.type}</span>${srcTag}<span class="tick">✓</span>${media}</div>
    ${note}
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
  // cache:no-store + cache-buster so we always read the CURRENT sha (stale sha => 409 on PUT)
  const r = await fetch(ghUrl(path) + `?ref=${gh.branch||"main"}&_=${Date.now()}`,
    { cache: "no-store",
      headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" } });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("GET " + r.status);
  return r.json();
}
async function ghPut(path, text, message) {
  // Retry on 409 (another session/push changed the file since we read its sha).
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

// ---- Per-scene B-roll upload: commit the file, then register it in scenes.json ----
// Reuses the connected GitHub token (contents:write). Uploaded clips are tagged
// source:"upload" so they're identifiable next to gathered + HeyGen footage.
function startUpload(sid) {
  if (!(gh && gh.token)) { toast("Connect GitHub first (top-right) to upload B-roll."); return; }
  let inp = $("#uploader");
  if (!inp) {
    inp = document.createElement("input");
    inp.type = "file"; inp.id = "uploader"; inp.accept = "video/*,image/*";
    inp.style.display = "none"; document.body.appendChild(inp);
  }
  inp.onchange = () => { const f = inp.files[0]; inp.value = ""; if (f) handleUpload(sid, f); };
  inp.click();
}

async function handleUpload(sid, file) {
  const isVid = file.type.startsWith("video") || /\.(mp4|webm|mov|m4v)$/i.test(file.name);
  if (file.size > 40 * 1024 * 1024) {
    if (!confirm(`"${file.name}" is ${(file.size/1048576).toFixed(0)} MB. Large files upload slowly through the GitHub API and bloat the repo. Continue?`)) return;
  }
  const clean = file.name.replace(/[^a-zA-Z0-9._-]/g, "-").replace(/-+/g, "-");
  const hasExt = isVid ? /\.(mp4|webm|mov|m4v)$/i.test(clean) : /\.(jpe?g|png|webp|gif)$/i.test(clean);
  const stem = `upload_${Date.now()}_${clean}${hasExt ? "" : (isVid ? ".mp4" : ".jpg")}`;
  const path = `projects/${state.slug}/previews/${sid}/${stem}`;
  toast("Uploading " + file.name + " …");
  try {
    const b64content = await fileToB64(file);
    await ghPutBinary(path, b64content, `cockpit: add B-roll to ${state.slug} ${sid}`);
    const clip = { id: stem.replace(/\.[^.]+$/, ""), type: isVid ? "video" : "image",
      source: "upload", author: "Uploaded", license: "Client-provided",
      note: file.name, thumb: isVid ? "" : path, preview: path };
    // register in the repo's scenes.json (read latest, prepend, write back)
    const got = await ghGet(`projects/${state.slug}/scenes.json`);
    const data = JSON.parse(decodeURIComponent(escape(atob(got.content))));
    const scenes = data.scenes || data;
    (scenes.find(s => s.id === sid) || {}).clips.unshift(clip);
    await ghPut(`projects/${state.slug}/scenes.json`, JSON.stringify(data, null, 2),
      `cockpit: register uploaded B-roll (${sid})`);
    // reflect immediately in the current view
    const ls = state.data.scenes.find(s => s.id === sid); if (ls) ls.clips.unshift(clip);
    render();
    toast(`✓ Added to ${sid} — visible to everyone after the Pages rebuild`);
  } catch (e) { toast("Upload failed: " + e.message); }
}

// ---- Drag & drop upload: each scene section is a drop zone that routes files
// through the SAME handleUpload flow the ＋ Add B-roll button uses.
const dragHasFiles = e => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
const isMediaFile = f => f.type.startsWith("video") || f.type.startsWith("image") ||
  /\.(mp4|webm|mov|m4v|jpe?g|png|webp|gif)$/i.test(f.name);

function wireDropZones(wrap) {
  wrap.querySelectorAll(".scene").forEach(sec => {
    const sid = sec.dataset.scene;
    let depth = 0; // dragenter/leave also fire on children; count to avoid flicker
    sec.addEventListener("dragenter", e => {
      if (!dragHasFiles(e)) return;
      e.preventDefault(); depth++;
      sec.classList.add("dropping");
    });
    sec.addEventListener("dragover", e => {
      if (!dragHasFiles(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    });
    sec.addEventListener("dragleave", () => {
      if (--depth <= 0) { depth = 0; sec.classList.remove("dropping"); }
    });
    sec.addEventListener("drop", e => {
      if (!dragHasFiles(e)) return;
      e.preventDefault();
      depth = 0; sec.classList.remove("dropping");
      handleDrop(sid, Array.from(e.dataTransfer.files));
    });
  });
}

async function handleDrop(sid, files) {
  if (!(gh && gh.token)) { toast("Connect GitHub first (top-right) to upload B-roll."); return; }
  const media = files.filter(isMediaFile);
  if (!media.length) { toast("Only video or image files can be added as B-roll."); return; }
  if (media.length < files.length) toast(`Skipping ${files.length - media.length} non-media file(s)…`);
  for (const f of media) await handleUpload(sid, f); // sequential — same flow as the ＋ button
}

// Don't let a stray drop outside a scene navigate the browser away.
["dragover", "drop"].forEach(ev =>
  window.addEventListener(ev, e => { if (dragHasFiles(e)) e.preventDefault(); }));

function fileToB64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1]); // strip the data: URL prefix
    r.onerror = () => rej(new Error("read error")); r.readAsDataURL(file);
  });
}

// Like ghPut but the content is already base64 (binary media, not text).
async function ghPutBinary(path, b64content, message) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const existing = await ghGet(path).catch(() => null);
    const body = { message, content: b64content, branch: gh.branch || "main" };
    if (existing && existing.sha) body.sha = existing.sha;
    const r = await fetch(ghUrl(path), { method: "PUT",
      headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" },
      body: JSON.stringify(body) });
    if (r.ok) return r.json();
    if (r.status === 409 && attempt < 3) { await new Promise(res => setTimeout(res, 500)); continue; }
    throw new Error("PUT " + r.status);
  }
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
$("#finalise").onclick = toggleFinalise;
if (gh && gh.token) { $("#savemode").textContent = `GitHub (${gh.owner}/${gh.repo})`; $("#connect").textContent = "Reconnect…"; }
loadProjects();
