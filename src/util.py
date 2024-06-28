import json
import logging
import sys

import colorlog


def get_logger(name):
    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(asctime)s %(log_color)s%(levelname)s%(reset)s %(message)s"
        )
    )
    logger = colorlog.getLogger(name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


CONF_FILENAME = "conf.json"


def get_conf():
    try:
        with open(CONF_FILENAME, encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        print(f"configure {CONF_FILENAME}")
        sys.exit(1)
