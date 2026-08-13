"""ASGI entry point with Semantic Runtime V2 connector composition."""

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from echo_masque.api import create_app
from echo_masque.runtime_upgrade import upgrade_semantic_runtime

app = create_app()
upgrade_semantic_runtime(app)


@app.middleware("http")
async def prevent_stale_portal_html(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if request.method == "GET" and content_type.startswith("text/html"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response
