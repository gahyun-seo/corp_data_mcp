import logging
import sys

def get_logger(name="mcp_db", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
        h.setFormatter(fmt)
        logger.addHandler(h)
    return logger
