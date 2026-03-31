import json
from datetime import datetime
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from config import ACCOUNT_SID, AUTH_TOKEN, TWILIO_FROM, openai_client, twilio_client
from state import conversation_store, collected_info
from topics import TOPICS
from helpers import get_voice, get_gather_language
from prompts import get_system_prompt
from email_helper import send_report_email

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/ai-gather", methods=['GET', 'POST'])
def ai_gather():
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "customer_service")
    call_sid = request.form.get("CallSid", request.args.get("CallSid", ""))
    voice    = get_voice(lang)
    gl       = get_gather_language(lang)

    resp = VoiceResponse()

    # Primera visita: inicializar historial y saludar
    if call_sid and call_sid not in conversation_store:
        caller_from = request.values.get("From", "")
        system_prompt = get_system_prompt(lang, topic, caller_from=caller_from)
        conversation_store[call_sid] = [{"role": "system", "content": system_prompt}]
        collected_info[call_sid] = {
            "name": None, "phone": None, "notes": None,
            "topic": topic, "lang": lang, "caller_from": caller_from,
        }

        greeting = TOPICS.get(topic, TOPICS["customer_service"]).get(lang, TOPICS[topic]["en"])["greeting"]
        conversation_store[call_sid].append({"role": "assistant", "content": greeting})
        resp.say(greeting, voice=voice)

    gather = Gather(
        input="speech",
        action=f"/ai-respond?lang={lang}&topic={topic}",
        method="POST",
        speech_timeout="auto",
        timeout=5,
        language=gl
    )
    resp.append(gather)

    silence = "I'm sorry, I didn't catch that. Please try again." if lang == "en" else "Lo siento, no le escuché. Por favor intente de nuevo."
    resp.say(silence, voice=voice)
    resp.redirect(f"/ai-gather?lang={lang}&topic={topic}")
    return str(resp)


@ai_bp.route("/ai-respond", methods=['GET', 'POST'])
def ai_respond():
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "customer_service")
    call_sid = request.form.get("CallSid", "")
    speech   = request.form.get("SpeechResult", "").strip()
    voice    = get_voice(lang)
    gl       = get_gather_language(lang)

    resp = VoiceResponse()

    if not speech:
        silence = "I'm sorry, I didn't catch that. Please try again." if lang == "en" else "Lo siento, no le escuché. Por favor intente de nuevo."
        resp.say(silence, voice=voice)
        resp.redirect(f"/ai-gather?lang={lang}&topic={topic}")
        return str(resp)

    # Inicializar si no existe (edge case)
    if call_sid not in conversation_store:
        caller_from = request.values.get("From", "")
        conversation_store[call_sid] = [{"role": "system", "content": get_system_prompt(lang, topic, caller_from=caller_from)}]
        collected_info[call_sid] = {
            "name": None, "phone": None, "notes": None,
            "topic": topic, "lang": lang, "caller_from": caller_from,
        }

    history = conversation_store[call_sid]
    history.append({"role": "user", "content": speech})

    # Llamar a OpenAI
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
            response_format={"type": "json_object"}
        )
        ai_json  = json.loads(completion.choices[0].message.content)
        message  = ai_json.get("message") or ("One moment please." if lang == "en" else "Un momento por favor.")
        name     = ai_json.get("name") or None
        phone    = ai_json.get("phone") or None
        notes    = ai_json.get("notes") or None
        end_call = ai_json.get("end_call", False)
        print(f"[AI] message={message!r} name={name!r} phone={phone!r} end_call={end_call!r}")
    except Exception as e:
        print(f"[AI ERROR] {e}")
        fallback = "I'm sorry, there was a technical issue. Please call back later." if lang == "en" else "Lo siento, hubo un problema técnico. Por favor llame más tarde."
        resp.say(fallback, voice=voice)
        resp.hangup()
        return str(resp)

    # Guardar solo el mensaje de texto — no el JSON completo, confunde al LLM
    history.append({"role": "assistant", "content": message})
    conversation_store[call_sid] = history

    # Actualizar info recolectada
    info = collected_info.get(call_sid, {"name": None, "phone": None, "notes": None, "topic": topic, "lang": lang})
    if name:
        info["name"] = name
    if phone:
        info["phone"] = phone
    if notes:
        info["notes"] = notes
    collected_info[call_sid] = info

    # Enviar WhatsApp cuando tengamos nombre y teléfono (solo una vez)
    if info["name"] and info["phone"] and not info.get("notified"):
        info["notified"] = True
        collected_info[call_sid] = info
        topic_label = TOPICS.get(topic, TOPICS["customer_service"]).get(lang, TOPICS[topic]["en"])["label"]
        lines = [
            f"📋 *Nueva consulta* — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📌 Tema: {topic_label}",
            f"🌐 Idioma: {'English' if lang == 'en' else 'Español'}",
            f"👤 Nombre: {info['name']}",
            f"📞 Teléfono: {info['phone']}",
        ]
        if info["notes"]:
            lines.append(f"📝 Notas: {info['notes']}")
        try:
            twilio_client().messages.create(
                from_=TWILIO_FROM,
                to="+14085900153",
                body="\n".join(lines),
            )
        except Exception as e:
            print(f"[WHATSAPP ERROR] {e}")

    if end_call:
        resp.say(message, voice=voice)
        # Guardar historial antes de limpiar (para el reporte final)
        history_snapshot = conversation_store.pop(call_sid, [])
        info["conversation"] = [m for m in history_snapshot if m["role"] != "system"]
        info["goodbye"] = message
        collected_info[call_sid] = info
        if topic != "schedule_callback" and info.get("name") and info.get("phone"):
            # Todas las opciones: conectar con operador humano tras recopilar datos
            base_url = request.url_root.rstrip("/")
            resp.redirect(f"{base_url}/connect-operator?lang={lang}&caller_sid={call_sid}")
        elif topic == "schedule_callback":
            # No hay operador disponible — imprimir fechas preferidas y colgar
            preferred = info.get("notes") or "(no times provided)"
            print(f"\n{'='*50}")
            print(f"[CALLBACK REQUEST] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Caller     : {info.get('caller_from', 'unknown')}")
            print(f"  Language   : {'English' if lang == 'en' else 'Español'}")
            print(f"  Preferred  : {preferred}")
            print(f"{'='*50}\n")
            send_report_email(
                subject=f"[IVR] Callback Request — {info.get('caller_from', 'unknown')}",
                body="\n".join([
                    f"CALLBACK REQUEST — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Caller    : {info.get('caller_from', 'unknown')}",
                    f"Language  : {'English' if lang == 'en' else 'Español'}",
                    f"Preferred : {preferred}",
                ]),
            )
            resp.hangup()
        else:
            resp.hangup()
    else:
        gather = Gather(
            input="speech",
            action=f"/ai-respond?lang={lang}&topic={topic}",
            method="POST",
            speech_timeout="auto",
            timeout=5,
            language=gl
        )
        gather.say(message, voice=voice)
        resp.append(gather)

        silence = "I'm sorry, I didn't catch that." if lang == "en" else "Lo siento, no le escuché."
        resp.say(silence, voice=voice)
        resp.redirect(f"/ai-gather?lang={lang}&topic={topic}")

    return str(resp)
