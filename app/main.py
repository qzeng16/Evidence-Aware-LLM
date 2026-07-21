from fastapi import FastAPI

from app.lifecycle import (
    application_lifespan,
)

from app.exception_handlers import (
    register_exception_handlers,
)
from app.observability import (
    RequestLoggingMiddleware,
)
from app.request_limits import (
    RequestBoundaryMiddleware,
)
from app.routes import router
from app.security_headers import (
    SecurityHeadersMiddleware,
)
from app.static_routes import router as static_router


app = FastAPI(
    lifespan=application_lifespan,
    title=(
        "Evidence-Aware Claim Verification API"
    ),
    description=(
        "A small evidence-aware verifier for "
        "Supported / Refuted / Uncertain claim "
        "classification."
    ),
    version="1.0.0",
)

app.add_middleware(
    RequestBoundaryMiddleware
)

app.add_middleware(
    RequestLoggingMiddleware
)

app.add_middleware(
    SecurityHeadersMiddleware
)

register_exception_handlers(app)




app.include_router(
    static_router
)

app.include_router(router)
