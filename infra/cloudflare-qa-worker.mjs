// qa.paktenops.com -> Cloud Run (kys-qa) ters vekil.
// Cloudflare panelinde ayrı bir Worker olarak yapıştırılır; paktenops.com'daki PaktenCare Worker'ına dokunmaz.
// Durum tutmaz, sır içermez. Kimlik doğrulama Cloud Run'daki uygulamanın Bearer token'ıdır.
const ORIGIN = "kys-qa-53duzoe3kq-ew.a.run.app";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "") {
      return Response.redirect(`${url.origin}/qa/app/`, 302);
    }
    const publicHost = url.host;
    url.protocol = "https:";
    url.hostname = ORIGIN;
    url.port = "";
    const resp = await fetch(new Request(url, request), { redirect: "manual" });
    // Cloud Run'ın mutlak yönlendirmeleri kullanıcıyı run.app adresine götürmesin.
    const loc = resp.headers.get("location");
    if (loc && loc.includes(ORIGIN)) {
      const fixed = new Response(resp.body, resp);
      fixed.headers.set("location", loc.replace(`https://${ORIGIN}`, `https://${publicHost}`));
      return fixed;
    }
    return resp;
  },
};
