// qa.paktenops.com -> Cloud Run (kys-qa) reverse proxy.
// Paste into the Cloudflare dashboard as a separate Worker (Edit code -> replace all -> Deploy).
// Does not touch the PaktenCare Worker on paktenops.com.
//
// Optional token-less use: add a Secret named KYS_TOKEN to this Worker. Requests without an
// Authorization header then get this token added. SECURITY: enable ONLY when Cloudflare Access protects
// qa.paktenops.com and the workers.dev URL is disabled. While KYS_TOKEN is set, workers.dev is refused.
// (File is ASCII-only on purpose, so it pastes cleanly into any editor.)

const ORIGIN = "kys-qa-53duzoe3kq-ew.a.run.app";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const publicHost = url.host;
    const token = env && env.KYS_TOKEN;

    if (token && publicHost.endsWith(".workers.dev")) {
      return new Response("This address is closed; use https://qa.paktenops.com", { status: 403 });
    }
    if (url.pathname === "/" || url.pathname === "") {
      return Response.redirect(url.origin + "/qa/app/", 302);
    }

    url.protocol = "https:";
    url.hostname = ORIGIN;
    url.port = "";

    const headers = new Headers(request.headers);
    if (token && !headers.get("authorization")) {
      headers.set("authorization", "Bearer " + token);
    }
    const init = {
      method: request.method,
      headers: headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    };
    const resp = await fetch(url.toString(), init);

    // Keep users on the public host when Cloud Run answers with an absolute redirect.
    const loc = resp.headers.get("location");
    if (loc && loc.indexOf(ORIGIN) !== -1) {
      const fixed = new Response(resp.body, resp);
      fixed.headers.set("location", loc.split("https://" + ORIGIN).join("https://" + publicHost));
      return fixed;
    }
    return resp;
  },
};
