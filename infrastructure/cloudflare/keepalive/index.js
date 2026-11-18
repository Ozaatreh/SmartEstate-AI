// Scheduled keep-alive: one GET to the public health endpoint. No secrets, no other requests.
export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(fetch(env.HEALTH_URL, { headers: { "user-agent": "smartestate-keepalive" } }).catch(() => undefined));
  },
};
