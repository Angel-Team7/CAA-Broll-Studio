// Music — the cockpit's music library. Same idea as the B-roll grid: listen, compare,
// shortlist. Tracks are listed in music/index.json (licence checked on each track's live
// page); previews stream from the source, nothing is re-hosted. The shortlist is a human
// choice and saves to music/picks.json with the same GitHub key as the cockpit.

const $ = s => document.querySelector(s);
const gh = JSON.parse(localStorage.getItem("gh") || "null");
const M = { tracks: [], picks: { shortlist: {} }, filter: "all", q: "", cur: null, order: [] };
const audio = new Audio();
audio.preload = "none";

const GROUPS = [
  { id: "all", label: "All" },
  { id: "cinematic", label: "Cinematic" },
  { id: "uplifting", label: "Uplifting" },
  { id: "piano", label: "Piano" },
  { id: "ambient", label: "Ambient" },
  { id: "sep" },
  { id: "use:intro", label: "For intros", tip: "Builds and lands — made for an opening or a brand intro" },
  { id: "bed:good", label: "Under a voice", tip: "Quiet, steady and soft enough to sit under narration" },
  { id: "sep" },
  { id: "short", label: "★ Shortlist" },
];

const esc = s => String(s ?? "").replace(/[&<>"]/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
const clock = t => { t = Math.max(0, Math.round(t || 0)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("show"), 2600); }

// ---------- load ----------
async function boot() {
  const idx = await fetchJSON("music/index.json");
  M.tracks = idx.tracks || [];
  $("#mucoll").textContent = idx.collection || "Music library";
  M.picks = (await fetchJSON("music/picks.json").catch(() => null)) || { shortlist: {} };
  try { Object.assign(M.picks.shortlist, JSON.parse(localStorage.getItem("musicShort") || "{}")); } catch {}
  const free = M.tracks.filter(t => !t.credit).length;
  $("#musummary").innerHTML = `<b>${M.tracks.length} tracks</b> — ${esc(idx.brief || "")}. ` +
    `<span class="lic free">${free} need no credit</span> <span class="lic credit">${M.tracks.length - free} need a credit line</span>`;
  $("#mufoot").textContent = (idx.note || "") + (idx.local_folder ? ` Full files: ${idx.local_folder}.` : "");
  renderFilters(); render(); saveState("idle");
}
async function fetchJSON(path) {
  if (gh && gh.token) {
    try {
      const r = await fetch(`https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${path}?ref=${gh.branch || "main"}&_=${Date.now()}`,
        { cache: "no-store", headers: { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github.raw+json" } });
      if (r.ok) return r.json();
      if (r.status === 404) return null;
    } catch {}
  }
  const r = await fetch(`${path}?v=${Date.now()}`, { cache: "no-store" });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

// ---------- filters ----------
function renderFilters() {
  $("#mufilters").innerHTML = GROUPS.map(g => g.id === "sep" ? '<span class="mf-sep"></span>' :
    `<button class="mf ${M.filter === g.id ? "on" : ""}" data-f="${g.id}" title="${esc(g.tip || "")}">${esc(g.label)}<i>${count(g.id)}</i></button>`).join("");
  $("#mufilters").querySelectorAll(".mf").forEach(b => b.onclick = () => { M.filter = b.dataset.f; renderFilters(); render(); });
}
function passes(t, f) {
  if (f === "all") return true;
  if (f === "short") return !!M.picks.shortlist[t.n];
  if (f.startsWith("use:")) return t.use === f.slice(4);
  if (f.startsWith("bed:")) return t.voice_bed === f.slice(4);
  return t.group === f;
}
function count(f) { return M.tracks.filter(t => passes(t, f)).length; }

// ---------- list ----------
function wave(t) {
  const p = t.peaks || [], w = 280, h = 34, bw = w / Math.max(1, p.length);
  return `<svg class="wv" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">${
    p.map((v, i) => { const bh = Math.max(1.5, v * h); return `<rect x="${(i * bw).toFixed(1)}" y="${((h - bh) / 2).toFixed(1)}" width="${Math.max(1, bw - 0.8).toFixed(1)}" height="${bh.toFixed(1)}"/>`; }).join("")
  }</svg>`;
}
function render() {
  const q = M.q.trim().toLowerCase();
  const rows = M.tracks.filter(t => passes(t, M.filter) &&
    (!q || [t.name, t.title, t.artist, t.mood, t.group, (t.tags || []).join(" ")].join(" ").toLowerCase().includes(q)));
  M.order = rows.map(t => t.n);
  $("#mulist").innerHTML = rows.length ? rows.map(t => {
    const on = M.picks.shortlist[t.n], playing = M.cur === t.n;
    const bed = t.voice_bed === "good" ? '<span class="chip bed" title="Soft and steady enough to sit under a voice">under a voice</span>'
              : t.voice_bed === "care" ? '<span class="chip care" title="Can sit under a voice if lowered 2–3 dB more than usual">voice: lower it</span>' : "";
    return `<article class="trk ${playing ? "playing" : ""} ${on ? "starred" : ""}" data-n="${t.n}">
      <button class="tplay" data-n="${t.n}" title="Play">${playing && !audio.paused ? "❚❚" : "▶"}</button>
      <div class="tinfo">
        <div class="tname"><span class="tnum">${String(t.n).padStart(2, "0")}</span>${esc(t.name)}</div>
        <div class="tsub">${esc(t.artist)} · <span class="tmood">${esc(t.mood)}</span></div>
        <div class="tchips"><span class="chip grp">${esc(t.group)}</span>${t.use === "intro" ? '<span class="chip intro" title="Builds and lands — made for an opening">intro</span>' : ""}${bed}</div>
      </div>
      <div class="twave" data-n="${t.n}" title="Click to jump">${wave(t)}<div class="tprog" style="width:${playing ? pct() : 0}%"></div></div>
      <div class="tdur">${clock(t.duration)}</div>
      <div class="tlic">${t.credit
        ? `<button class="lic credit copycredit" data-n="${t.n}" title="Credit required. Click to copy the credit line:\n${esc(t.credit)}">CC BY · copy credit</button>`
        : `<span class="lic free" title="Public domain (CC0) — no credit needed">CC0 · no credit</span>`}
        <a class="tsrc" href="${esc(t.page_url)}" target="_blank" rel="noopener">source ↗</a></div>
      <button class="tstar ${on ? "on" : ""}" data-n="${t.n}" title="${on ? "On the shortlist — click to remove" : "Add to the shortlist"}">${on ? "★" : "☆"}</button>
    </article>`;
  }).join("") : '<p class="muted pad">Nothing matches this filter.</p>';
  const L = $("#mulist");
  L.querySelectorAll(".tplay").forEach(b => b.onclick = () => togglePlay(+b.dataset.n));
  L.querySelectorAll(".twave").forEach(w => w.onclick = e => {
    const n = +w.dataset.n, r = w.getBoundingClientRect(), f = (e.clientX - r.left) / r.width;
    if (M.cur !== n) play(n, f); else if (audio.duration) audio.currentTime = f * audio.duration;
  });
  L.querySelectorAll(".tstar").forEach(b => b.onclick = () => star(+b.dataset.n));
  L.querySelectorAll(".copycredit").forEach(b => b.onclick = () => copyCredit(+b.dataset.n));
}

// ---------- playback ----------
const byN = n => M.tracks.find(t => t.n === n);
function pct() { return audio.duration ? (100 * audio.currentTime / audio.duration) : 0; }
function play(n, from) {
  const t = byN(n); if (!t) return;
  if (M.cur !== n) { audio.src = t.preview; M.cur = n; }
  const go = () => { if (from != null && audio.duration) audio.currentTime = from * audio.duration; };
  if (from != null) audio.addEventListener("loadedmetadata", go, { once: true });
  audio.play().then(go).catch(() => toast("This preview would not play — the source may have withdrawn it."));
  $("#muplayer").hidden = false;
  $("#mptitle").textContent = t.name; $("#mpartist").textContent = " · " + t.artist;
  render();
}
function togglePlay(n) {
  if (n == null) n = M.cur;
  if (n == null) return;
  if (M.cur === n && !audio.paused) { audio.pause(); render(); return; }
  play(n);
}
function next(dir = 1) {
  if (!M.order.length) return;
  const i = M.order.indexOf(M.cur);
  play(M.order[(i + dir + M.order.length) % M.order.length]);
}
audio.addEventListener("timeupdate", () => {
  const p = pct();
  $("#mpfill").style.width = p + "%";
  $("#mptime").textContent = `${clock(audio.currentTime)} / ${clock(audio.duration)}`;
  const el = document.querySelector(`.trk[data-n="${M.cur}"] .tprog`); if (el) el.style.width = p + "%";
});
audio.addEventListener("play", () => { $("#mpplay").textContent = "❚❚"; syncBtn(); });
audio.addEventListener("pause", () => { $("#mpplay").textContent = "▶"; syncBtn(); });
audio.addEventListener("ended", () => next(1));
function syncBtn() { const b = document.querySelector(`.tplay[data-n="${M.cur}"]`); if (b) b.textContent = audio.paused ? "▶" : "❚❚"; }
$("#mpplay").onclick = () => togglePlay();
$("#mpnext").onclick = () => next(1);
$("#mpbar").onclick = e => { const r = e.currentTarget.getBoundingClientRect(); if (audio.duration) audio.currentTime = (e.clientX - r.left) / r.width * audio.duration; };
document.addEventListener("keydown", e => {
  if (/INPUT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); togglePlay(M.cur ?? M.order[0]); }
  if (e.key === "ArrowDown") { e.preventDefault(); next(1); }
  if (e.key === "ArrowUp") { e.preventDefault(); next(-1); }
});

// ---------- shortlist + credit ----------
async function star(n) {
  const s = M.picks.shortlist;
  if (s[n]) delete s[n]; else s[n] = { at: new Date().toISOString(), name: byN(n).name };
  try { localStorage.setItem("musicShort", JSON.stringify(s)); } catch {}
  renderFilters(); render();
  if (!(gh && gh.token)) { saveState("off"); return; }
  saveState("saving");
  try {
    await ghPut("music/picks.json", JSON.stringify({ shortlist: s, updated: new Date().toISOString() }, null, 2),
                "music: shortlist " + (s[n] ? "+ " : "− ") + byN(n).name);
    saveState("saved");
  } catch (e) { saveState("error"); toast("Could not save to GitHub: " + e.message); }
}
async function copyCredit(n) {
  const t = byN(n);
  try { await navigator.clipboard.writeText(t.credit); toast("Credit line copied — paste it in the video description or end credits"); }
  catch { prompt("Copy this credit line:", t.credit); }
}
function saveState(k) {
  const el = $("#musave");
  const s = !(gh && gh.token) ? ["off", "Not connected — shortlist stays in this browser"]
          : k === "saving" ? ["busy", "Saving…"] : k === "error" ? ["bad", "⚠ Not saved"]
          : k === "saved" ? ["ok", "Shortlist saved"] : ["ok", "Connected"];
  el.className = "connpill " + s[0]; el.innerHTML = `<span class="dot"></span>${s[1]}`;
}
async function ghPut(path, text, message) {
  const url = `https://api.github.com/repos/${gh.owner}/${gh.repo}/contents/${path}`;
  const H = { Authorization: `Bearer ${gh.token}`, Accept: "application/vnd.github+json" };
  for (let i = 0; i < 4; i++) {
    const cur = await fetch(`${url}?ref=${gh.branch || "main"}&_=${Date.now()}`, { cache: "no-store", headers: H });
    const sha = cur.ok ? (await cur.json()).sha : undefined;
    const r = await fetch(url, { method: "PUT", headers: H, body: JSON.stringify({
      message, branch: gh.branch || "main", content: btoa(unescape(encodeURIComponent(text))), ...(sha ? { sha } : {}) }) });
    if (r.ok) return;
    if (r.status !== 409 && r.status !== 422) throw new Error("PUT " + r.status);
  }
  throw new Error("PUT conflict");
}

$("#muq").oninput = e => { M.q = e.target.value; render(); };
boot().catch(e => { $("#mulist").innerHTML = `<p class="pad">Could not load the music list (${esc(e.message)}).</p>`; });
