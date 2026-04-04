import json
import os

USE_CASES_PATH = os.path.join(os.path.dirname(__file__), "use_cases.json")

_cache = {}


def _load_use_cases():
    if "data" not in _cache:
        with open(USE_CASES_PATH, encoding="utf-8") as f:
            _cache["data"] = json.load(f)
    return _cache["data"]


def save_use_case(use_case_id: str, updated_uc: dict):
    use_cases = _load_use_cases()
    use_cases[use_case_id] = updated_uc
    with open(USE_CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(use_cases, f, ensure_ascii=False, indent=2)
    _cache.clear()


def get_active_use_case() -> dict:
    import runtime_config
    use_case_id = runtime_config.get("use_case_id", os.environ.get("USE_CASE_ID", "robles_ai"))
    use_cases = _load_use_cases()
    if use_case_id not in use_cases:
        print(f"[USE_CASE] '{use_case_id}' not found, falling back to 'robles_ai'")
        use_case_id = "robles_ai"
    return use_cases[use_case_id]


def get_company_name() -> str:
    return get_active_use_case()["name"]


def get_topics() -> dict:
    """Returns a TOPICS-compatible dict for the active use case plus special topics."""
    uc = get_active_use_case()
    company = uc["name"]
    topics = {}

    for topic_id, topic_data in uc["topics"].items():
        topics[topic_id] = {
            "en": {
                "label":       topic_data["en"]["label"],
                "greeting":    topic_data["en"]["greeting"],
                "system_extra": topic_data["en"]["system_extra"],
                "questions":   topic_data["en"].get("questions", []),
                "menu_text":   topic_data["en"].get("menu_text", ""),
                "meeting_type": topic_data.get("meeting_type", False),
                "digit":       topic_data.get("digit", ""),
            },
            "es": {
                "label":       topic_data["es"]["label"],
                "greeting":    topic_data["es"]["greeting"],
                "system_extra": topic_data["es"]["system_extra"],
                "questions":   topic_data["es"].get("questions", []),
                "menu_text":   topic_data["es"].get("menu_text", ""),
                "meeting_type": topic_data.get("meeting_type", False),
                "digit":       topic_data.get("digit", ""),
            },
        }

    # Special built-in topics
    topics["schedule_callback"] = {
        "en": {
            "label": "Schedule Callback",
            "greeting": (
                f"I'm sorry, our team at {company} is not available at this moment. "
                "I'd like to schedule a callback for you. "
                "Could you tell me at least one preferred date and time for us to call you back?"
            ),
            "system_extra": (
                f"The caller tried to reach {company} but no one is available. "
                "Collect at least one preferred date and time for a callback. "
                "Allow multiple options. Once collected, confirm and say goodbye."
            ),
            "questions": [],
            "menu_text": "",
            "meeting_type": False,
            "digit": "",
        },
        "es": {
            "label": "Agendar Rellamada",
            "greeting": (
                f"Lo sentimos, nuestro equipo de {company} no está disponible en este momento. "
                "Me gustaría agendar una rellamada para usted. "
                "¿Podría indicarme al menos una fecha y hora de su preferencia para que le llamemos?"
            ),
            "system_extra": (
                f"El llamante intentó comunicarse con {company} pero no hay nadie disponible. "
                "Recopile al menos una fecha y hora preferida para una rellamada. "
                "Permita varias opciones. Una vez recopiladas, confírmelas y despídase."
            ),
            "questions": [],
            "menu_text": "",
            "meeting_type": False,
            "digit": "",
        },
    }

    topics["direct"] = {
        "en": {"label": "Direct Transfer (Whitelisted)", "greeting": "", "system_extra": "", "questions": [], "menu_text": "", "meeting_type": False, "digit": ""},
        "es": {"label": "Transferencia Directa (Lista Blanca)", "greeting": "", "system_extra": "", "questions": [], "menu_text": "", "meeting_type": False, "digit": ""},
    }

    return topics


def get_digit_to_topic() -> dict:
    """Maps digit string → topic_id for the active use case."""
    uc = get_active_use_case()
    return {v["digit"]: k for k, v in uc["topics"].items() if v.get("digit")}
