// broll media proxy — a Cloudflare Worker (free plan is plenty).
//
// Why it exists: GitHub serves every Release asset as `application/octet-stream` with
// `x-content-type-options: nosniff` and no CORS. Chrome and Firefox sniff the bytes and
// play the MP4 anyway; Safari refuses to play media that is not labelled as media. This
// worker fetches the same file from the Release and re-serves it as video/mp4 (or the
// right image type), with byte-range support (Safari asks for ranges) and CORS.
//
// Deploy once: Cloudflare dashboard → Workers & Pages → Create → "Hello World" → Edit
// code → replace everything with this file → Deploy. Then put the worker URL into
// projects.json as  "media_proxy": "https://<name>.<account>.workers.dev"  — the cockpit
// routes every preview and thumbnail through it automatically.

const UPSTREAM = "https://github.com/Angel-Team7/CAA-Broll-Studio/releases/download/";
const TYPES = { mp4: "video/mp4", m4v: "video/mp4", webm: "video/webm", mov: "video/quicktime",
                jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif" };
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
               "Access-Control-Allow-Headers": "Range", "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges" };

export default {
  async fetch(req) {
    const url = new URL(req.url);
    const path = decodeURIComponent(url.pathname.replace(/^\/+/, ""));      // media-<slug>/<asset>
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (!/^media-[\w.-]+\/[^/]+$/.test(path)) return new Response("not found", { status: 404, headers: CORS });
    const type = TYPES[path.split(".").pop().toLowerCase()];
    if (!type) return new Response("unsupported type", { status: 415, headers: CORS });

    // Cloudflare's edge cache keeps the whole file after the first request. (On the
    // free workers.dev domain the Cache API may be unavailable — then every request just
    // goes upstream, which is still fine for 0.3–3 MB previews.)
    let cache = null; try { cache = caches.default; } catch {}
    const key = new Request(url.origin + "/" + path, { method: "GET" });
    let full = cache ? await cache.match(key).catch(() => null) : null;
    if (!full) {
      const up = await fetch(UPSTREAM + path, { redirect: "follow", cf: { cacheEverything: true, cacheTtl: 31536000 } });
      if (!up.ok) return new Response(`upstream ${up.status}`, { status: 502, headers: CORS });
      const buf = await up.arrayBuffer();
      full = new Response(buf, { status: 200, headers: { "Content-Type": type, "Content-Length": String(buf.byteLength),
               "Cache-Control": "public, max-age=31536000, immutable", "Accept-Ranges": "bytes", ...CORS } });
      if (cache) { try { await cache.put(key, full.clone()); } catch {} }
    }
    const buf = await full.arrayBuffer();
    const total = buf.byteLength;
    const base = { "Content-Type": type, "Cache-Control": "public, max-age=31536000, immutable", "Accept-Ranges": "bytes", ...CORS };
    if (req.method === "HEAD") return new Response(null, { status: 200, headers: { ...base, "Content-Length": String(total) } });

    const range = req.headers.get("Range");
    const m = range && /^bytes=(\d*)-(\d*)$/.exec(range.trim());
    if (m) {
      let start, end;
      if (m[1] === "" && m[2] !== "") { start = Math.max(0, total - Number(m[2])); end = total - 1; }   // suffix range
      else { start = Number(m[1] || 0); end = m[2] === "" ? total - 1 : Math.min(Number(m[2]), total - 1); }
      if (start >= total || start > end)
        return new Response(null, { status: 416, headers: { ...base, "Content-Range": `bytes */${total}` } });
      return new Response(buf.slice(start, end + 1), { status: 206, headers: { ...base,
               "Content-Range": `bytes ${start}-${end}/${total}`, "Content-Length": String(end - start + 1) } });
    }
    return new Response(buf, { status: 200, headers: { ...base, "Content-Length": String(total) } });
  }
};
