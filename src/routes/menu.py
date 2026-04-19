from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather

import db
from state import collected_info
from helpers import get_voice, format_phone_spoken
from whitelist import is_whitelisted
from use_case_loader import get_active_use_case, get_digit_to_topic, get_company_name

menu_bp = Blueprint("menu", __name__)


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
    slogan  = uc.get("slogan", {}).get("en", "")

    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-en", method="POST")
    greeting = f"Thank you for calling {company}. {slogan} Please listen to the following options." if slogan else f"Thank you for calling {company}. Please listen to the following options."
    gather.say(greeting, voice=get_voice("en"))
    for opt in options:
        if opt["digit"] == "1":
            gather.say(opt["menu_text"], voice=get_voice("en"))
            gather.say("Para Español, presione 2.", voice=get_voice("es"))
        else:
            gather.say(opt["menu_text"], voice=get_voice("en"))
    resp.append(gather)
    resp.redirect("/menu")
    return str(resp)


@menu_bp.route("/handle-en", methods=['GET', 'POST'])
def handle_en():
    digit          = request.form.get("Digits", "")
    resp           = VoiceResponse()
    digit_to_topic = get_digit_to_topic()

    if digit == "2":
        resp.redirect("/menu-es")
    elif digit == "*":
        resp.redirect("/demo-code-gather?lang=en")
    elif digit in digit_to_topic:
        topic = digit_to_topic[digit]
        resp.redirect(f"/ai-gather?lang=en&topic={topic}")
    else:
        resp.say("That is not a valid option. Please try again.", voice=get_voice("en"))
        resp.redirect("/menu")
    return str(resp)


@menu_bp.route("/menu-es", methods=['GET', 'POST'])
def menu_es():
    uc      = get_active_use_case()
    options = _sorted_options(uc, "es")
    company = get_company_name()
    slogan  = uc.get("slogan", {}).get("es", "")

    resp = VoiceResponse()
    resp.play(request.url_root + "intro.wav")

    gather = Gather(num_digits=1, action="/handle-es", method="POST")
    greeting = f"Gracias por llamar a {company}. {slogan} Por favor escuche las siguientes opciones." if slogan else f"Gracias por llamar a {company}. Por favor escuche las siguientes opciones."
    gather.say(greeting, voice=get_voice("es"))
    for opt in options:
        if opt["digit"] == "1":
            gather.say(opt["menu_text"], voice=get_voice("es"))
            gather.say("Press 2 for English.", voice=get_voice("en"))
        else:
            gather.say(opt["menu_text"], voice=get_voice("es"))
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
    elif digit == "*":
        resp.redirect("/demo-code-gather?lang=es")
    elif digit in digit_to_topic:
        topic = digit_to_topic[digit]
        resp.redirect(f"/ai-gather?lang=es&topic={topic}")
    else:
        resp.say("Esa no es una opción válida. Por favor intente de nuevo.", voice=get_voice("es"))
        resp.redirect("/menu-es")
    return str(resp)


@menu_bp.route("/demo-code-gather", methods=['GET', 'POST'])
def demo_code_gather():
    lang = request.args.get("lang", "en")
    resp = VoiceResponse()
    voice_en = get_voice("en")
    voice_es = get_voice("es")

    gather = Gather(num_digits=6, action=f"/demo-code-handle?lang={lang}",
                    method="POST", timeout=10, finish_on_key="#")
    if lang == "es":
        gather.say("Ingresa tu código de demo de 6 dígitos, seguido de gato.", voice=voice_es)
    else:
        gather.say("Please enter your 6-digit demo code followed by pound.", voice=voice_en)
    resp.append(gather)

    if lang == "es":
        resp.say("No recibimos ningún código. Regresando al menú principal.", voice=voice_es)
    else:
        resp.say("We did not receive a code. Returning to the main menu.", voice=voice_en)
    resp.redirect("/menu")
    return str(resp)


@menu_bp.route("/demo-code-handle", methods=['GET', 'POST'])
def demo_code_handle():
    lang      = request.args.get("lang", "en")
    code      = request.form.get("Digits", "").strip()
    call_sid  = request.form.get("CallSid", "")
    caller_from = request.form.get("From", "")
    resp      = VoiceResponse()
    voice_en  = get_voice("en")
    voice_es  = get_voice("es")

    demo_uc = db.uc_get_by_demo_code(code)
    if not demo_uc:
        if lang == "es":
            resp.say("Código de demo no válido. Por favor intente de nuevo.", voice=voice_es)
        else:
            resp.say("Invalid demo code. Please try again.", voice=voice_en)
        resp.redirect(f"/demo-code-gather?lang={lang}")
        return str(resp)

    demo_id  = demo_uc["id"]
    ivr_type = demo_uc.get("ivr_type", "topics")

    if ivr_type == "conversational":
        # Go directly to AI conversation (no digit menu)
        resp.redirect(f"/ai-gather?lang={lang}&topic=_conversational&demo_id={demo_id}")
    else:
        # Topics mode: show the demo's own menu
        options = _sorted_options(demo_uc, lang)
        slogan  = demo_uc.get("slogan", {}).get(lang, "")
        company = demo_uc["name"]
        voice   = get_voice(lang)

        gather = Gather(num_digits=1, action=f"/demo-handle-topic?lang={lang}&demo_id={demo_id}",
                        method="POST")
        greeting = (
            f"{'Bienvenido' if lang == 'es' else 'Welcome'} to {company}. {slogan} "
            f"{'Por favor escuche las opciones.' if lang == 'es' else 'Please listen to the following options.'}"
        ).strip()
        gather.say(greeting, voice=voice)
        for opt in options:
            gather.say(opt["menu_text"], voice=voice)
        resp.append(gather)
        resp.redirect(f"/demo-code-gather?lang={lang}")
    return str(resp)


@menu_bp.route("/demo-handle-topic", methods=['GET', 'POST'])
def demo_handle_topic():
    lang    = request.args.get("lang", "en")
    demo_id = request.args.get("demo_id", "")
    digit   = request.form.get("Digits", "")
    resp    = VoiceResponse()

    demo_uc = db.uc_get(demo_id)
    if not demo_uc:
        resp.redirect("/menu")
        return str(resp)

    digit_to_topic = {v["digit"]: k for k, v in demo_uc["topics"].items() if v.get("digit")}
    voice = get_voice(lang)

    if digit in digit_to_topic:
        topic = digit_to_topic[digit]
        resp.redirect(f"/ai-gather?lang={lang}&topic={topic}&demo_id={demo_id}")
    else:
        msg = "Opción no válida." if lang == "es" else "Invalid option."
        resp.say(msg, voice=voice)
        resp.redirect(f"/demo-code-gather?lang={lang}")
    return str(resp)
