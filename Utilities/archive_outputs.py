import logging
import shutil
from datetime import datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Utilities.app_logging import setup_logging


TARGET_DIRECTORIES = [
    PROJECT_ROOT / "CrossRef" / "results",
    PROJECT_ROOT / "Webscraper" / "output",
    PROJECT_ROOT / "Webscraper" / "results",
    PROJECT_ROOT / "LLM" / "results",
    PROJECT_ROOT / "Combinator" / "output",
    PROJECT_ROOT / "Combinator" / "results",
]


def ensure_directory(path):
    path.mkdir(parents=True, exist_ok=True)


def archive_directory(source_dir, archive_root):
    ensure_directory(source_dir)
    destination_dir = archive_root / source_dir.parent.name / source_dir.name
    ensure_directory(destination_dir)

    archived_anything = False

    for item in source_dir.iterdir():
        shutil.move(str(item), str(destination_dir / item.name))
        archived_anything = True

    logging.info(
        "Archived directory source=%s destination=%s archived_anything=%s",
        source_dir,
        destination_dir,
        archived_anything,
    )

    return {
        "source": str(source_dir),
        "destination": str(destination_dir),
        "archived_anything": archived_anything,
    }


def archive_all_outputs():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = PROJECT_ROOT / "Old-outputs" / timestamp
    ensure_directory(archive_root)

    summary = []
    for source_dir in TARGET_DIRECTORIES:
        summary.append(archive_directory(source_dir, archive_root))

    return archive_root, summary


def main():
    log_file = setup_logging()
    logging.info("Archive outputs utility started")
    print(f"Logging to {log_file}")

    archive_root, summary = archive_all_outputs()
    print(f"Archived outputs to: {archive_root}")

    for item in summary:
        print(
            f"- {item['source']} -> {item['destination']} "
            f"(archived_anything={item['archived_anything']})"
        )


if __name__ == "__main__":
    main()
