// qa.paktenops.com -> Cloud Run (kys-qa) ters vekil.
// Cloudflare panelinde ayrı bir Worker olarak yapıştırılır; paktenops.com'daki PaktenCare Worker'ına dokunmaz.
//
// Token'sız kullanım (isteğe bağlı): Worker'a KYS_TOKEN adlı bir "Secret" eklenirse, Authorization başlığı
// olmayan isteklere bu token eklenir; kullanıcı token girmez. GÜVENLİK: bunu YALNIZCA Cloudflare Access
// (Zero Trust) uygulaması qa.paktenops.com'u koruyorken ve workers.dev adresi KAPALIYKEN açın; aksi halde
// adresi bilen herkes verilere erişir. Bu yüzden KYS_TOKEN varken workers.dev'den gelen istek reddedilir.
const ORIGIN = "kys-qa-53duzoe3kq-ew.a.run.app";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const publicHost = url.host;
    if (env.KYS_TOKEN && publicHost.endsWith(".workers.dev")) {
      return new Response("Bu adres kapalı; qa.paktenops.com kullanın.", { status: 403 });
    }
    if (url.pathname === "/" || url.pathname === "") {
      return Response.redirect(`${url.origin}/qa/app/`, 302);
    }
    url.protocol = "https:";
    url.hostname = ORIGIN;
    url.port = "";
    const upstream = new Request(url, request);
    if (env.KYS_TOKEN && !upstream.headers.get("authorization")) {
      upstream.headers.set("authorization", `Bearer ${env.KYS_TOKEN}`);
    }
    const resp = await fetch(upstream, { redirect: "manual" });
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
