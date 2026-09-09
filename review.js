// Review Desk — the 360p drafts the overnight desk left for the reviewer.
// Each draft: watch, drop timestamped notes, pick a bed, then Approve (→ 1080 render) or
// Request changes (→ a Claude session reads the notes and re-cuts). Decisions are written to
// reviews/<slug>.json with the same GitHub key the cockpit uses; desk.py polls that file.
const $ = s => document.querySelector(s);
const gh = JSON.parse(localStorage.getItem("gh") || "null");
const RELEASE_BASE = "https://github.com/Angel-Team7/CAA-Broll-Studio/releases/download/";
let mediaProxy = "";
const state = { items: [], docs: {}, open: null };

function toast(msg, ms) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), ms || 2600);
}
const esc = s => (s || "").replace(/[&<>"]/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;" }[m]));
const b64 = s => btoa(unescape(encodeURIComponent(s)));
const fmt = t => { const n = Math.max(0, Math.floor(Number(t) || 0)); return `${Math.floor(n/60)}:${String(n%60).padStart(2,"0")}`; };
function mediaUrl(u) {
  if (!u || !mediaProxy || !u.startsWith(RELEASE_BASE)) return u || "";
  return mediaProxy.replace(/\/+$/, "") + "/" + u.slice(RELEASE_BASE.length);
}
function ghUrl(path) { return `https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${path}`; }
async function ghGet(path) {
  const r = await fetch(ghUrl(path) + `?ref=${gh.branch||"main"}&_=${Date.now()}`,
    { cache: "no-store", headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" } });
  if (r.status === 404) return null; if (!r.ok) throw new Error("GET " + r.status); return r.json();
}
async function ghPut(path, text, message) {
  for (let attempt = 0; attempt < 4; attempt++) {
    const existing = await ghGet(path).catch(() => null);
    const body = { message, content: b64(text), branch: gh.branch || "main" };
    if (existing && existing.sha) body.sha = existing.sha;
    const r = await fetch(ghUrl(path), { method: "PUT",
      headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" }, body: JSON.stringify(body) });
    if (r.ok) return r.json();
    if (r.status === 409 && attempt < 3) { await new Promise(res => setTimeout(res, 500)); continue; }
    throw new Error("PUT " + r.status);
  }
}

async function load() {
  const idx = await fetch("projects.json?v=" + Date.now(), { cache: "no-store" }).then(r => r.json()).catch(() => ({}));
  mediaProxy = (idx.media_proxy || "").trim();
  const ri = await fetch("reviews/index.json?v=" + Date.now(), { cache: "no-store" }).then(r => r.json()).catch(() => null);
  if (!ri || !ri.items.length) { $("#view").innerHTML = '<p class="pad muted">Nothing on the desk yet. The overnight desk publishes each 360p draft here when it is ready.</p>'; return; }
  state.items = ri.items;
  for (const it of state.items) {
    let doc = null;
    if (gh && gh.token) { const got = await ghGet(`reviews/${it.slug}.json`).catch(() => null); if (got) { try { doc = JSON.parse(atob(got.content)); } catch {} } }
    if (!doc) doc = await fetch(`reviews/${it.slug}.json?v=${Date.now()}`, { cache: "no-store" }).then(r => r.json()).catch(() => null);
    if (doc) state.docs[it.slug] = doc;
  }
  $("#localwarn").hidden = !!(gh && gh.token);
  if (gh && gh.token) $("#savemode").textContent = `GitHub (${gh.owner}/${gh.repo})`;
  render();
}

const STATUS = { awaiting_review: ["🟡 Waiting for your review", "wait"], changes_requested: ["🟠 Changes requested — being re-cut", "chg"],
                 rendering_final: ["🔵 Approved — rendering the 1080", "fin"], approved: ["🔵 Approved", "fin"], delivered: ["🟢 Delivered", "done"] };

function render() {
  const waiting = state.items.filter(i => i.status === "awaiting_review").length;
  $("#stat").textContent = waiting ? `${waiting} video${waiting > 1 ? "s" : ""} waiting for you` : "nothing waiting";
  document.title = (waiting ? `(${waiting}) ` : "") + "Edenrise Review Desk";
  $("#view").innerHTML = state.items.map(it => {
    const d = state.docs[it.slug]; if (!d) return "";
    const [label, cls] = STATUS[d.status] || [d.status, ""];
    const openMe = state.open === it.slug || (state.open === null && d.status === "awaiting_review");
    const music = d.music || { candidates: [] };
    const chosen = music.chosen || music.preselected || "none";
    const notes = (d.comments || []).filter(c => (c.version || d.version) === d.version);
    const canDecide = d.status === "awaiting_review";
    return `<section class="rv ${cls}" data-slug="${it.slug}">
      <div class="rvhead" data-toggle="${it.slug}">
        <div><div class="rvtitle">${esc(d.title)} <span class="muted">· ${d.lang.toUpperCase()} · v${d.version} · ${fmt(d.duration)}</span></div>
          <div class="rvstatus">${label}${d.decided ? ` <span class="muted">· ${esc(d.decided.slice(0,16).replace("T"," "))}</span>` : ""}</div></div>
        <div class="muted small">${openMe ? "▾" : "▸"}</div>
      </div>
      ${openMe ? `<div class="rvbody">
        <div class="rvmain">
          <video class="rvplayer" controls preload="metadata" playsinline src="${esc(mediaUrl(d.draft_url))}" poster="${esc(mediaUrl(d.contact_url) || "")}"></video>
          ${d.final_url ? `<p class="small">Final 1080: <a href="${esc(mediaUrl(d.final_url))}" target="_blank" rel="noopener">download</a></p>` : ""}
          ${d.contact_url ? `<details class="small"><summary>Contact sheet</summary><img class="contact" src="${esc(mediaUrl(d.contact_url))}" alt="contact sheet"></details>` : ""}
          <div class="gates small">${gatesLine(d)}</div>
          ${(d.fetch_notes || []).length ? `<div class="small warnline">⚠ ${d.fetch_notes.map(esc).join(" · ")}</div>` : ""}
          ${d.adapt_changes ? `<details class="small"><summary>Script adaptation log</summary><pre class="pre">${esc(d.adapt_changes)}</pre></details>` : ""}
        </div>
        <div class="rvside">
          <h4>Notes for the editor</h4>
          <ul class="notes">${notes.length ? notes.map((c, i) => `<li><b class="tcode" data-seek="${c.t}">${fmt(c.t)}</b> ${esc(c.text)} ${canDecide ? `<button class="linkbtn delnote" data-i="${i}">✕</button>` : ""}</li>`).join("") : '<li class="muted">No notes yet.</li>'}</ul>
          ${canDecide ? `<div class="noterow"><button class="stamp" title="Take the time from the player">⏱ <span class="stampt">0:00</span></button>
            <input class="notetxt" type="text" placeholder="What should change here?"><button class="addnote">Add</button></div>` : ""}
          <h4>Music bed</h4>
          <div class="beds">
            ${music.candidates.map(c => `<label class="bed ${chosen === c.key ? "on" : ""}"><input type="radio" name="bed-${it.slug}" value="${esc(c.key)}" ${chosen === c.key ? "checked" : ""} ${canDecide ? "" : "disabled"}>
               <span><b>${esc(c.name)}</b> <span class="muted">${esc(c.instruments)} · LRA ${c.lra}${(c.used_by||[]).length ? " · already used by " + esc(c.used_by.join(", ")) : ""}</span></span>
               ${c.preview ? `<audio controls preload="none" src="${esc(mediaUrl(c.preview))}"></audio>` : ""}</label>`).join("")}
            <label class="bed ${chosen === "none" ? "on" : ""}"><input type="radio" name="bed-${it.slug}" value="none" ${chosen === "none" ? "checked" : ""} ${canDecide ? "" : "disabled"}><span><b>No music</b> <span class="muted">voice only</span></span></label>
          </div>
          ${canDecide ? `<div class="decide">
            <button class="approve">✓ Approve → render 1080</button>
            <button class="changes">✎ Request changes</button>
          </div>` : `<p class="muted small">Decision recorded${d.music && d.music.chosen ? " · bed: " + esc(d.music.chosen) : ""}.</p>`}
        </div>
      </div>` : ""}
    </section>`;
  }).join("");
  document.querySelectorAll("[data-toggle]").forEach(el => el.onclick = () => { state.open = state.open === el.dataset.toggle ? "-" : el.dataset.toggle; render(); });
  document.querySelectorAll(".rv").forEach(sec => wire(sec));
}

function gatesLine(d) {
  const g = d.gates || {}; const parts = Object.keys(g).map(k => `${g[k] ? "✅" : "❌"} ${k}`);
  return parts.length ? parts.join(" · ") + (d.gate_warns ? ` · ${d.gate_warns} warn(s) triaged` : "") : "";
}

function wire(sec) {
  const slug = sec.dataset.slug; const d = state.docs[slug]; const video = sec.querySelector(".rvplayer");
  const stamp = sec.querySelector(".stamp"); const stampt = sec.querySelector(".stampt");
  if (video && stampt) video.ontimeupdate = () => stampt.textContent = fmt(video.currentTime);
  if (stamp) stamp.onclick = () => { if (video) video.pause(); stampt.textContent = fmt(video ? video.currentTime : 0); sec.querySelector(".notetxt").focus(); };
  sec.querySelectorAll(".tcode").forEach(el => el.onclick = () => { if (video) { video.currentTime = Number(el.dataset.seek) || 0; video.play(); } });
  const add = sec.querySelector(".addnote");
  if (add) {
    const go = () => {
      const txt = sec.querySelector(".notetxt").value.trim(); if (!txt) return;
      d.comments = d.comments || []; d.comments.push({ t: Math.floor(video ? video.currentTime : 0), text: txt, version: d.version, ts: new Date().toISOString() });
      sec.querySelector(".notetxt").value = ""; render(); persist(slug, "note");
    };
    add.onclick = go; sec.querySelector(".notetxt").onkeydown = e => { if (e.key === "Enter") go(); };
  }
  sec.querySelectorAll(".delnote").forEach(el => el.onclick = () => {
    const mine = (d.comments || []).filter(c => (c.version || d.version) === d.version); const victim = mine[Number(el.dataset.i)];
    d.comments = d.comments.filter(c => c !== victim); render(); persist(slug, "note");
  });
  sec.querySelectorAll(`input[name="bed-${slug}"]`).forEach(r => r.onchange = () => { d.music = d.music || {}; d.music.chosen = r.value; render(); });
  const ap = sec.querySelector(".approve"), ch = sec.querySelector(".changes");
  if (ap) ap.onclick = async () => {
    d.music = d.music || {}; d.music.chosen = (sec.querySelector(`input[name="bed-${slug}"]:checked`) || {}).value || d.music.preselected || "none";
    if (!confirm(`Approve v${d.version} of "${d.title}" and render the 1080 with bed "${d.music.chosen}"?`)) return;
    d.decision = "approve"; d.decided = new Date().toISOString(); d.status = "approved";
    render(); await persist(slug, "approve");
  };
  if (ch) ch.onclick = async () => {
    const mine = (d.comments || []).filter(c => (c.version || d.version) === d.version);
    if (!mine.length) { toast("Add at least one note first — the editor needs to know what to change."); return; }
    if (!confirm(`Send ${mine.length} note(s) on v${d.version} back to the editor?`)) return;
    d.decision = "changes"; d.decided = new Date().toISOString(); d.status = "changes_requested";
    render(); await persist(slug, "changes");
  };
}

async function persist(slug, why) {
  const d = state.docs[slug];
  if (gh && gh.token) {
    try {
      await ghPut(`reviews/${slug}.json`, JSON.stringify(d, null, 1), `review: ${why} ${slug} v${d.version}`);
      toast(why === "note" ? "Note saved" : why === "approve" ? "Approved ✓ — the desk will render the 1080" : "Sent back to the editor");
    } catch (e) { toast("GitHub save failed: " + e.message); }
  } else {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(d, null, 1)], { type: "application/json" }));
    a.download = `${slug}.review.json`; a.click(); URL.revokeObjectURL(a.href);
    toast("Not connected — downloaded the decision file instead. Send it to Vic.");
  }
}
load();
