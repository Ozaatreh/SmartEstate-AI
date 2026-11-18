/**
 * Cloudflare Pages Function helper: forwards a request to the SmartEstate API (Render) on the same path, so the
 * browser only ever talks to this site's own origin (first-party cookies, no CORS). API_ORIGIN is a Pages
 * environment variable, e.g. https://smartestate-api.onrender.com — no secrets live here.
 */
export async function proxy(request, env) {
  const origin = env.API_ORIGIN;
  if (!origin) {
    return Response.json({ error: { code: "proxy_not_configured", message: "The API address isn't configured." } }, { status: 503 });
  }
  const url = new URL(request.url);
  const target = new URL(url.pathname + url.search, origin);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-forwarded-for"); // never trust a client-supplied value
  const ip = request.headers.get("cf-connecting-ip"); // set by Cloudflare for the real visitor
  if (ip) headers.set("x-forwarded-for", ip);
  headers.set("x-forwarded-proto", "https");
  headers.set("x-forwarded-host", url.host);
  const res = await fetch(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual",
  });
  // Stream the response back unchanged (Server-Sent Events for the assistant included).
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers: res.headers });
}
