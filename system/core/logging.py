
import logging, sys

import warnings
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy",
    category=UserWarning
)


def setup_logger():
    logger = logging.getLogger("sisap")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

LOGGER = setup_logger()
