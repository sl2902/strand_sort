# scripts/try_extract.py
import base64
import sys
from pathlib import Path

from loguru import logger

from strand_sort.vision.extract import get_extractor


def load_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def main():
    image_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/cleaned")
    logger.info(f"Accessing directory {image_dir}")

    for item_folder in sorted(image_dir.iterdir()):
        logger.info(f"Accessing folder {item_folder}")
        if not item_folder.is_dir():
            continue

        files_list = sorted(item_folder.glob("*.jpg")) + sorted(item_folder.glob("*.png"))
        images = [load_image_b64(p) for p in files_list]
        if not images:
            continue

        logger.info(f"Testing {item_folder.name} ({len(images)} images)")
        result = get_extractor(images)
        logger.info(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()