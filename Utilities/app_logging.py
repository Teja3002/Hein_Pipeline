from datetime import datetime
from pathlib import Path
import logging


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"


def setup_logging() -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | pid=%(process)d | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return log_file
