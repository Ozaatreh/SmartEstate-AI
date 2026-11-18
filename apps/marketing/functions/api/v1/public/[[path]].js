// Only the public API is reachable through the website's origin; every other /api path is not proxied here.
import { proxy } from "../../../_proxy.js";

export const onRequest = ({ request, env }) => proxy(request, env);
