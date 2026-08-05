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
 * KV also holds:
 *   additions  -> { pid: {name, role: "child"|"partner", anchor: <pid>,
 *                          birthday..., editor, createdAt} }
 *   (pids of added people are prefixed "x-"; only those can be deleted)
 *
 * Routes:
 *   GET    /api/familytree/overrides      -> the full overrides doc
 *   PUT    /api/familytree/person/<pid>   -> save one person's fields
 *   GET    /api/familytree/additions      -> the additions doc
 *   POST   /api/familytree/additions      -> add a person (child/partner)
 *   PUT    /api/familytree/additions/<pid>    -> edit an added person's name
 *   DELETE /api/familytree/additions/<pid>    -> remove an added person
 */

const FIELDS = ["birthday", "phone", "email", "addr1", "addr2"];

function slugify(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "").slice(0, 40) || "person";
}

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

    if (url.pathname === "/api/familytree/additions") {
      if (request.method === "GET") {
        const doc = await env.FT_KV.get("additions");
        return json(doc ? JSON.parse(doc) : {});
      }
      if (request.method === "POST") {
        let body;
        try {
          body = await request.json();
        } catch (_) {
          return json({ error: "bad json" }, 400);
        }
        const name = String(body.name || "").trim().slice(0, 80);
        const role = body.role === "partner" ? "partner" : "child";
        const anchor = String(body.anchor || "");
        if (!name || !/^[a-z0-9-]+$/.test(anchor)) {
          return json({ error: "name and anchor required" }, 400);
        }
        const pid = "x-" + slugify(name) + "-" +
                    Date.now().toString(36).slice(-4);
        const entry = { name, role, anchor,
                        createdAt: new Date().toISOString(),
                        editor: String(body.editor || "").slice(0, 40) };
        for (const f of FIELDS) {
          if (body[f]) entry[f] = String(body[f]).slice(0, 200);
        }
        const doc = JSON.parse((await env.FT_KV.get("additions")) || "{}");
        doc[pid] = entry;
        await env.FT_KV.put("additions", JSON.stringify(doc));
        await env.FT_KV.put(`hist:${pid}:${Date.now()}`,
                            JSON.stringify({ added: entry }));
        return json({ ok: true, pid, person: entry });
      }
    }

    const am = url.pathname.match(
      /^\/api\/familytree\/additions\/(x-[a-z0-9-]+)$/);
    if (am) {
      const pid = am[1];
      const doc = JSON.parse((await env.FT_KV.get("additions")) || "{}");
      if (!doc[pid]) return json({ error: "not found" }, 404);
      if (request.method === "DELETE") {
        const removed = doc[pid];
        delete doc[pid];
        await env.FT_KV.put("additions", JSON.stringify(doc));
        await env.FT_KV.put(`hist:${pid}:${Date.now()}`,
                            JSON.stringify({ removed }));
        return json({ ok: true });
      }
      if (request.method === "PUT") {
        let body;
        try {
          body = await request.json();
        } catch (_) {
          return json({ error: "bad json" }, 400);
        }
        if (body.name) doc[pid].name = String(body.name).trim().slice(0, 80);
        doc[pid].editor = String(body.editor || "").slice(0, 40);
        await env.FT_KV.put("additions", JSON.stringify(doc));
        await env.FT_KV.put(`hist:${pid}:${Date.now()}`,
                            JSON.stringify({ renamed: doc[pid] }));
        return json({ ok: true, person: doc[pid] });
      }
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
