# scripts/try_clean.py
import sys
from pathlib import Path

from loguru import logger

from strand_sort.vision.clean import clean_image


def main():
    input_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw")
    output_dir = Path("data/cleaned")
    output_dir.mkdir(parents=True, exist_ok=True)

    for item_folder in sorted(input_dir.iterdir()):
        if not item_folder.is_dir():
            continue

        out_folder = output_dir / item_folder.name
        out_folder.mkdir(exist_ok=True)

        for img_path in sorted(item_folder.glob("*.jpg")) + sorted(item_folder.glob("*.png")):
            logger.info(f"Cleaning {img_path}")
            cleaned = clean_image(img_path.read_bytes())
            out_path = out_folder / f"{img_path.stem}_cleaned.jpg"
            out_path.write_bytes(cleaned)
            logger.info(f"-> {out_path}")


if __name__ == "__main__":
    main()