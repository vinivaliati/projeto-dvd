"""Refuse state-changing requests that a page from another site could send.

The algorithm of Go's CrossOriginProtection: trust Sec-Fetch-Site when the browser sends it;
otherwise compare Origin with Host; with neither header the request did not come from a
browser, so it cannot be a cross-site forgery.
"""

from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def same_origin(headers: Headers) -> bool:
    site = headers.get("sec-fetch-site")
    if site is not None:
        return site in ("same-origin", "none")
    origin = headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == headers.get("host")


class SameOriginMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] not in SAFE_METHODS
            and not same_origin(Headers(scope=scope))
        ):
            response = PlainTextResponse("Pedido de outro site recusado.", status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
