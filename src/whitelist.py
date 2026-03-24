import json
import os

WHITELIST_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "whitelist.json")
)


def load_whitelist() -> set:
    try:
        with open(WHITELIST_PATH) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def is_whitelisted(phone: str) -> bool:
    return phone in load_whitelist()
