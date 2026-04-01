from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather

from state import collected_info
from helpers import get_voice, format_phone_spoken
from whitelist import is_whitelisted
from use_case_loader import get_active_use_case, get_digit_to_topic, get_company_name

menu_bp = Blueprint("menu", __name__)

EN_VOICE = "Google.en-US-Neural2-D"
ES_VOICE = "Google.es-US-Neural2-B"


def _sorted_options(uc, lang):
    """Returns topic options sorted by digit for the given language."""
    return sorted(
        [
            {"topic_id": tid, "digit": tdata["digit"], **tdata[lang]}
            for tid, tdata in uc["topics"].items()
            if tdata.get("digit")
        ],
        key=lambda x: x["digit"],
    )


@menu_bp.route("/menu", methods=['GET', 'POST'])
def main_menu():
    caller_from = request.values.get("From", "")
    call_sid    = request.values.get("CallSid", "")
    base_url    = request.url_root.rstrip("/")

    if caller_from and is_whitelisted(caller_from):
        print(f"[WHITELIST] Direct transfer for {caller_from}")
        collected_info[call_sid] = {
            "name": format_phone_spoken(caller_from),
            "phone": caller_from,
            "notes": "Direct transfer — whitelisted number",
            "topic": "direct",
            "lang": "en",
            "caller_from": caller_from,
        }
        resp = VoiceResponse()
        resp.redirect(f"{base_url}/connect-operator?lang=en&caller_sid={call_sid}")
        return str(resp)

    uc      = get_active_use_case()
    options = _sorted_options(uc, "en")
    company = get_company_name()

    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-en", method="POST")
    gather.say(f"Thank you for calling {company}. Please listen to the following options.", voice=EN_VOICE)
    for opt in options:
        if opt["digit"] == "1":
            gather.say(opt["menu_text"], voice=EN_VOICE)
            gather.say("Para Español, presione 2.", voice=ES_VOICE)
        else:
            gather.say(opt["menu_text"], voice=EN_VOICE)
    resp.append(gather)
    resp.redirect("/menu")
    return str(resp)


@menu_bp.route("/handle-en", methods=['GET', 'POST'])
def handle_en():
    digit        = request.form.get("Digits", "")
    resp         = VoiceResponse()
    digit_to_topic = get_digit_to_topic()

    if digit == "2":
        resp.redirect("/menu-es")
    elif digit in digit_to_topic:
        topic = digit_to_topic[digit]
        resp.redirect(f"/ai-gather?lang=en&topic={topic}")
    else:
        resp.say("That is not a valid option. Please try again.", voice=EN_VOICE)
        resp.redirect("/menu")
    return str(resp)


@menu_bp.route("/menu-es", methods=['GET', 'POST'])
def menu_es():
    uc      = get_active_use_case()
    options = _sorted_options(uc, "es")
    company = get_company_name()

    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-es", method="POST")
    gather.say(f"Gracias por llamar a {company}. Por favor escuche las siguientes opciones.", voice=ES_VOICE)
    for opt in options:
        if opt["digit"] == "1":
            gather.say(opt["menu_text"], voice=ES_VOICE)
            gather.say("Press 2 for English.", voice=EN_VOICE)
        else:
            gather.say(opt["menu_text"], voice=ES_VOICE)
    resp.append(gather)
    resp.redirect("/menu-es")
    return str(resp)


@menu_bp.route("/handle-es", methods=['GET', 'POST'])
def handle_es():
    digit          = request.form.get("Digits", "")
    resp           = VoiceResponse()
    digit_to_topic = get_digit_to_topic()

    if digit == "2":
        resp.redirect("/menu")
    elif digit in digit_to_topic:
        topic = digit_to_topic[digit]
        resp.redirect(f"/ai-gather?lang=es&topic={topic}")
    else:
        resp.say("Esa no es una opción válida. Por favor intente de nuevo.", voice=ES_VOICE)
        resp.redirect("/menu-es")
    return str(resp)
