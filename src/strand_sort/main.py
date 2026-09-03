import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from strand_sort.config import settings
from strand_sort.api import intake, inventory, review

app = FastAPI(
    title="Food Bank Inventory & Intake API",
    version="1.0.0",
    description="Idempotent intake agent and cross-database inventory service.",
)

# Local dev origins are always allowed; the deployed frontend origin (if any)
# is added on top via FRONTEND_ORIGIN so this works both locally and in the demo.
_allowed_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
if settings.frontend_origin:
    _allowed_origins.add(settings.frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.storage_backend == "local":
    os.makedirs(settings.image_storage_local_path, exist_ok=True)
    app.mount("/images", StaticFiles(directory=settings.image_storage_local_path), name="images")

app.include_router(intake.router, prefix="/api/v1", tags=["intake"])
app.include_router(inventory.router, prefix="/api/v1", tags=["inventory"])
app.include_router(review.router, prefix="/api/v1", tags=["review"])


