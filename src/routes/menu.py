from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather

from state import collected_info
from helpers import format_phone_spoken
from whitelist import is_whitelisted

menu_bp = Blueprint("menu", __name__)


@menu_bp.route("/", methods=['GET', 'POST'])
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

    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-en", method="POST")
    gather.say(
        "Thank you for calling Robles AI! "
        "Press 1 to Schedule a Meeting. ",
        voice="Google.en-US-Neural2-D"
    )
    gather.say(
        "Presione 2 para español. ",
        voice="Google.es-US-Neural2-B"
    )
    gather.say(
        "Press 3 for Artificial Intelligence and Machine Learning Services. "
        "Press 4 for Computer Vision Services. "
        "Press 5 for Customer Service.",
        voice="Google.en-US-Neural2-D"
    )
    resp.append(gather)
    resp.redirect("/")
    return str(resp)


@menu_bp.route("/handle-en", methods=['GET', 'POST'])
def handle_en():
    digit = request.form.get("Digits", "")
    resp  = VoiceResponse()
    topic_map = {"1": "meeting", "3": "ai_ml", "4": "computer_vision", "5": "customer_service"}
    wait_map  = {"1": 1, "3": 3, "4": 4, "5": 5}

    if digit == "2":
        resp.redirect("/menu-es")
    elif digit in topic_map:
        resp.redirect(f"/ai-gather?lang=en&topic={topic_map[digit]}")
    else:
        resp.say("That is not a valid option. Please try again.", voice="Google.en-US-Neural2-D")
        resp.redirect("/")

    return str(resp)


@menu_bp.route("/menu-es", methods=['GET', 'POST'])
def menu_es():
    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-es", method="POST")
    gather.say(
        "Presione 1 para Agendar una Reunión. ",
        voice="Google.es-US-Neural2-B"
    )
    gather.say(
        "Press 2 for English. ",
        voice="Google.en-US-Neural2-D"
    )
    gather.say(
        "Presione 3 para Servicios de Inteligencia Artificial y Machine Learning. "
        "Presione 4 para Servicios de Visión por Computadora. "
        "Presione 5 para Servicio al Cliente.",
        voice="Google.es-US-Neural2-B"
    )
    resp.append(gather)
    resp.redirect("/menu-es")
    return str(resp)


@menu_bp.route("/handle-es", methods=['GET', 'POST'])
def handle_es():
    digit = request.form.get("Digits", "")
    resp  = VoiceResponse()
    topic_map = {"1": "meeting", "3": "ai_ml", "4": "computer_vision", "5": "customer_service"}
    wait_map  = {"1": 1, "3": 3, "4": 4, "5": 5}

    if digit == "2":
        resp.redirect("/")
    elif digit in topic_map:
        resp.redirect(f"/ai-gather?lang=es&topic={topic_map[digit]}")
    else:
        resp.say("Esa no es una opción válida. Por favor intente de nuevo.", voice="Google.es-US-Neural2-B")
        resp.redirect("/menu-es")

    return str(resp)
