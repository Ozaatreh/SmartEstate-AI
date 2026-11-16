"""Request context (request ID + access log) and CSRF protection for cookie-authenticated requests."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_var

log = logging.getLogger("app.request")
SAFE_ID = re.compile(r"^[A-Za-z0-9\-_.]{8,64}$")
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = b"x-requested-with"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "%s %s %s", scope["method"], scope["path"], status_holder["code"],
                extra={"duration_ms": round((time.perf_counter() - started) * 1000, 1), "status": status_holder["code"]},
            )
            request_id_var.reset(token)


class CsrfHeaderMiddleware:
    """Mutating API requests must carry ``X-Requested-With: XMLHttpRequest``.

    Browsers cannot add custom headers to cross-site form posts, and CORS blocks them for
    scripts from other origins, so together with SameSite=Lax cookies this stops CSRF.
    """

    def __init__(self, app: ASGIApp, prefix: str = "/api/"):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and scope["path"].startswith(self.prefix)
            and dict(scope["headers"]).get(CSRF_HEADER, b"").lower() != b"xmlhttprequest"
        ):
            from app.core.handlers import error_response  # local import avoids a cycle

            response = error_response(
                403, "csrf_header_missing", "This request is missing the X-Requested-With header."
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
