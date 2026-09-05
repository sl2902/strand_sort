import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from strand_sort.config import settings
from strand_sort.api import intake, inventory, review, uploads
from strand_sort.db.repository import get_inventory_repository
from strand_sort.storage.image_storage import check_local_image_integrity, resolve_local_storage_path

logger = logging.getLogger("strand_sort.startup")


def _check_image_integrity_on_startup() -> None:
    """Runs on every server start AND every --reload restart — exactly the
    trigger that previously orphaned images (a relative storage path
    resolving against a different cwd across restarts). Logs a loud warning
    immediately if any stored image reference no longer resolves to a real
    file, instead of waiting for someone to notice a blank thumbnail."""
    if settings.storage_backend != "local":
        return
    try:
        items = get_inventory_repository().list_all()
    except Exception as e:
        logger.warning("Image integrity check skipped — couldn't read inventory: %s", e)
        return

    missing = check_local_image_integrity(resolve_local_storage_path(), items)
    if missing:
        logger.warning(
            "IMAGE INTEGRITY CHECK FAILED: %d stored image reference(s) point to files that no "
            "longer exist under %s. This is the exact symptom of the storage-path/cwd bug — if "
            "you didn't just delete these files by hand, check how the server was started.\n  %s",
            len(missing), resolve_local_storage_path(), "\n  ".join(missing),
        )
    elif items:
        logger.info("Image integrity check passed — all stored image references resolved OK.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_image_integrity_on_startup()
    yield


app = FastAPI(
    title="Food Bank Inventory & Intake API",
    version="1.0.0",
    description="Idempotent intake agent and cross-database inventory service.",
    lifespan=lifespan,
)

# Local dev origins are always allowed; the deployed frontend origin (if any)
# is added on top via FRONTEND_ORIGIN so this works both locally and in the demo.
_allowed_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
if settings.frontend_origin:
    _allowed_origins.add(settings.frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #list(_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.storage_backend == "local":
    # Same resolution as LocalImageStorage.save_images — anchored to the
    # package's location on disk, not the process cwd, so the save path and
    # this serve path can never diverge across restarts.
    _local_image_path = resolve_local_storage_path()
    os.makedirs(_local_image_path, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(_local_image_path)), name="images")

app.include_router(intake.router, prefix="/api/v1", tags=["intake"])
app.include_router(inventory.router, prefix="/api/v1", tags=["inventory"])
app.include_router(review.router, prefix="/api/v1", tags=["review"])
app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])

