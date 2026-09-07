"""
Captures a real image (or set of images) through the same extraction path
used elsewhere (get_extractor) and writes the result out as a demo-mode
fixture — same JSON shape and frontend/public/demo/ layout that
build_part1_fixtures used for the eggs/wheat atta fixtures, and that
frontend/src/pages/DemoPage.tsx reads via manifest.json. Dropping a fixture
in this way requires zero frontend code changes: DemoPage discovers
whatever names are listed in manifest.json.

Usage:
    uv run scripts/capture_demo_fixture.py path/to/photo1.jpg path/to/photo2.jpg
    uv run scripts/capture_demo_fixture.py --name golden-flagged-item photo.jpg
"""
import argparse
import base64
import json
import sys
from pathlib import Path

from loguru import logger

from strand_sort.vision.extract import get_extractor
from strand_sort.vision.thumbnail import generate_thumbnail
from strand_sort.expiry import compute_expiry_status

# scripts/ -> repo root. Anchored to this file's location, not the process's
# cwd, so the fixture always lands in the same place regardless of where
# `uv run` is invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "frontend" / "public" / "demo"
MANIFEST_PATH = DEMO_DIR / "manifest.json"
LARGE_MAX_DIMENSION = 1600
DEFAULT_NAME = "golden-flagged-item"


def load_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def load_manifest() -> list[str]:
    if not MANIFEST_PATH.exists():
        return []
    return json.loads(MANIFEST_PATH.read_text()).get("fixtures", [])


def save_manifest(fixtures: list[str]) -> None:
    MANIFEST_PATH.write_text(json.dumps({"fixtures": fixtures}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path, help="Local image file path(s) to scan")
    parser.add_argument(
        "--name",
        default=DEFAULT_NAME,
        help=f"Fixture name, used for the JSON filename and image filenames (default: {DEFAULT_NAME})",
    )
    args = parser.parse_args()

    for path in args.images:
        if not path.is_file():
            logger.error(f"Not a file: {path}")
            sys.exit(1)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    images_base64 = [load_image_b64(p) for p in args.images]
    logger.info(f"Extracting from {len(images_base64)} image(s)…")
    item = get_extractor(images_base64)

    # Same safety rule as the Part 1 fixtures: a demo fixture must never
    # carry a real, potentially-colliding inventory item_id, since
    # InventoryItemCard's delete button calls the live DELETE API directly —
    # an accidental click during a demo recording must 404 harmlessly, not
    # touch a real row.
    item.item_id = f"demo-{args.name}"

    # get_extractor doesn't populate expiry_status/is_expired — that's
    # normally computed on API read. Compute it once, now, the same way
    # Part 1's fixtures did.
    status = compute_expiry_status(item.expiration_date)
    item.expiry_status = status
    item.is_expired = status is not None and status.value == "expired"

    image_urls = []
    thumbnail_urls = []
    copied_paths = []
    for i, src_path in enumerate(args.images):
        orig_bytes = src_path.read_bytes()

        large_bytes = generate_thumbnail(orig_bytes, max_dimension=LARGE_MAX_DIMENSION)
        large_dest = DEMO_DIR / f"{args.name}-{i}.jpg"
        large_dest.write_bytes(large_bytes)
        image_urls.append(f"/demo/{args.name}-{i}.jpg")
        copied_paths.append(large_dest)

        thumb_bytes = generate_thumbnail(orig_bytes)  # default 400px, matches app convention
        thumb_dest = DEMO_DIR / f"{args.name}-thumb-{i}.jpg"
        thumb_dest.write_bytes(thumb_bytes)
        thumbnail_urls.append(f"/demo/{args.name}-thumb-{i}.jpg")
        copied_paths.append(thumb_dest)

    item.image_urls = image_urls
    item.thumbnail_urls = thumbnail_urls

    fixture_path = DEMO_DIR / f"{args.name}.json"
    fixture_path.write_text(item.model_dump_json(indent=2) + "\n")

    fixtures = load_manifest()
    if args.name not in fixtures:
        fixtures.append(args.name)
        save_manifest(fixtures)

    rel_fixture = fixture_path.relative_to(REPO_ROOT)
    rel_images = [p.relative_to(REPO_ROOT) for p in copied_paths]

    print(f"Fixture written: {rel_fixture}")
    print(f"Images copied: {', '.join(str(p) for p in rel_images)}")
    print(f"Manifest updated: {MANIFEST_PATH.relative_to(REPO_ROOT)} -> {fixtures}")
    if item.requires_human_review:
        print(f"Item was flagged: True | reason: {item.review_reason}")
    else:
        print(
            "Item was flagged: False — this photo read cleanly and was NOT flagged for review. "
            "The fixture was still written, but if you specifically wanted a flagged/Review "
            "example, try a different or worse-quality photo (blurry date, damaged packaging, "
            "unreadable label) and re-run."
        )


if __name__ == "__main__":
    main()
