import json
import os

WHITELIST_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "whitelist.json")
)


def load_whitelist() -> list:
    try:
        with open(WHITELIST_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_whitelist(numbers: list):
    with open(WHITELIST_PATH, "w") as f:
        json.dump(numbers, f, indent=2)


def is_whitelisted(phone: str) -> bool:
    return phone in load_whitelist()


def add_number(phone: str):
    numbers = load_whitelist()
    if phone not in numbers:
        numbers.append(phone)
        _save_whitelist(numbers)


def remove_number(phone: str):
    numbers = load_whitelist()
    numbers = [n for n in numbers if n != phone]
    _save_whitelist(numbers)
