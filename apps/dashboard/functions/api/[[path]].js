// The staff dashboard talks to the whole API through its own origin (the API enforces sign-in and permissions).
import { proxy } from "../_proxy.js";

export const onRequest = ({ request, env }) => proxy(request, env);
