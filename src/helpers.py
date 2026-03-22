def get_voice(lang):
    return "Google.en-US-Neural2-D" if lang == "en" else "Google.es-US-Neural2-B"


def get_gather_language(lang):
    return "en-US" if lang == "en" else "es-US"


def format_phone_spoken(phone):
    """Format a phone number for TTS: e.g. +14085900153 → 408-590-0153."""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits[0] == '1':
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return '-'.join(digits[i:i+3] for i in range(0, len(digits), 3))
