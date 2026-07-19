from fastapi import FastAPI

from app.routes import router
from app.services import initialize_service


app = FastAPI(
    title="Evidence-Aware Claim Verification API",
    description="A small evidence-aware verifier for Supported / Refuted / Uncertain claim classification.",
    version="1.0.0"
)


@app.on_event("startup")
def startup_event() -> None:
    initialize_service()


app.include_router(router)
