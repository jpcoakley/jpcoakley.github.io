/* familytree-api — Cloudflare Worker
 *
 * Live edit layer for jpcoakley.com/familytree. The static page decrypts the
 * base data client-side, then overlays these overrides. All requests must
 * carry the family password in the X-FT-Pass header (matched against the
 * FT_PASS Worker secret).
 *
 * KV (binding FT_KV):
 *   overrides            -> { pid: {birthday, phone, email, addr1, addr2,
 *                                   updatedAt, editor} }
 *   hist:<pid>:<ts>      -> one JSON entry per saved edit (audit/recovery)
 *
 * Routes:
 *   GET /api/familytree/overrides      -> the full overrides doc
 *   PUT /api/familytree/person/<pid>   -> save one person's fields
 */

const FIELDS = ["birthday", "phone", "email", "addr1", "addr2"];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if ((request.headers.get("X-FT-Pass") || "").trim().toLowerCase() !==
        env.FT_PASS) {
      return json({ error: "unauthorized" }, 401);
    }

    if (request.method === "GET" &&
        url.pathname === "/api/familytree/overrides") {
      const doc = await env.FT_KV.get("overrides");
      return json(doc ? JSON.parse(doc) : {});
    }

    const m = url.pathname.match(/^\/api\/familytree\/person\/([a-z0-9-]+)$/);
    if (request.method === "PUT" && m) {
      const pid = m[1];
      let body;
      try {
        body = await request.json();
      } catch (_) {
        return json({ error: "bad json" }, 400);
      }
      const entry = { updatedAt: new Date().toISOString(),
                      editor: String(body.editor || "").slice(0, 40) };
      for (const f of FIELDS) {
        if (f in body) entry[f] = String(body[f] || "").slice(0, 200);
      }
      const doc = JSON.parse((await env.FT_KV.get("overrides")) || "{}");
      doc[pid] = Object.assign({}, doc[pid], entry);
      await env.FT_KV.put("overrides", JSON.stringify(doc));
      await env.FT_KV.put(`hist:${pid}:${Date.now()}`,
                          JSON.stringify(entry));
      return json({ ok: true, person: doc[pid] });
    }

    return json({ error: "not found" }, 404);
  },
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json",
               "Cache-Control": "no-store" },
  });
}
