import json
from datetime import datetime
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from config import ACCOUNT_SID, AUTH_TOKEN, openai_client, twilio_client
import runtime_config
import reports
from state import conversation_store, collected_info
from use_case_loader import get_topics, get_active_use_case
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
        # Preserve pre-screening info when redirected (e.g. from main flow to schedule_callback)
        prior = collected_info.get(call_sid, {})
        collected_info[call_sid] = {
            "name":                prior.get("name"),
            "phone":               prior.get("phone"),
            "notes":               None,
            "topic":               prior.get("topic") or topic,
            "lang":                lang,
            "caller_from":         prior.get("caller_from") or caller_from,
            "notified":            prior.get("notified"),
            "conversation":        prior.get("conversation"),
            "operator_briefing":   prior.get("operator_briefing"),
            "goodbye":             prior.get("goodbye"),
        }

        TOPICS = get_topics()
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
        TOPICS = get_topics()
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
        wa_from = runtime_config.get("whatsapp_from") or ""
        wa_to   = runtime_config.get("whatsapp_to")   or ""
        if runtime_config.get("notify_whatsapp") == "1" and wa_from and wa_to:
            try:
                twilio_client().messages.create(
                    from_=f"whatsapp:{wa_from}",
                    to=f"whatsapp:{wa_to}",
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
            preferred  = info.get("notes") or "(no times provided)"
            base_url   = request.url_root.rstrip("/")
            uc         = get_active_use_case()
            company    = uc.get("name", "")
            TOPICS     = get_topics()
            orig_topic = info.get("topic") or topic
            topic_label = TOPICS.get(orig_topic, {}).get(lang, {}).get("label") or \
                          TOPICS.get(orig_topic, {}).get("en", {}).get("label") or \
                          ("Callback Request" if lang == "en" else "Solicitud de Rellamada")

            # Merge pre-screening conversation + callback scheduling conversation
            prescreening_conv = info.get("conversation") or []
            callback_conv     = [m for m in history_snapshot if m["role"] != "system"]
            full_conversation = prescreening_conv + callback_conv

            report_data = {
                "timestamp":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "use_case":               company,
                "caller_name":            info.get("name") or info.get("caller_from", ""),
                "caller_phone":           info.get("phone") or info.get("caller_from", ""),
                "topic":                  topic_label,
                "language":               "English" if lang == "en" else "Español",
                "conversation":           full_conversation,
                "operator_briefing":      info.get("operator_briefing", ""),
                "transcription":          "",
                "transcription_segments": [],
                "summary":                f"{'Callback requested' if lang == 'en' else 'Rellamada solicitada'}. {'Preferred times' if lang == 'en' else 'Horas preferidas'}: {preferred}",
                "goodbye":                info.get("goodbye", ""),
            }
            report_id  = reports.save(report_data)
            report_url = f"{base_url}/report/{report_id}"
            print(f"[CALLBACK REPORT] Saved: {report_url}")

            send_report_email(
                subject=f"[IVR] Callback Request — {info.get('caller_from', 'unknown')}",
                body="\n".join([
                    f"CALLBACK REQUEST — {report_data['timestamp']}",
                    f"Caller    : {report_data['caller_name']} / {report_data['caller_phone']}",
                    f"Language  : {report_data['language']}",
                    f"Preferred : {preferred}",
                    f"",
                    f"View report: {report_url}",
                ]),
            )

            if runtime_config.get("notify_whatsapp") == "1":
                wa_from = runtime_config.get("whatsapp_from") or ""
                wa_to   = runtime_config.get("whatsapp_to")   or ""
                if wa_from and wa_to:
                    wa_body = "\n".join([
                        f"📞 *Callback Request* — {report_data['timestamp']}",
                        f"🏢 {company}",
                        f"👤 {report_data['caller_name']} / {report_data['caller_phone']}",
                        f"🕐 {preferred}",
                        f"",
                        f"🔗 {report_url}",
                    ])
                    try:
                        twilio_client().messages.create(
                            from_=f"whatsapp:{wa_from}",
                            to=f"whatsapp:{wa_to}",
                            body=wa_body,
                        )
                        print(f"[WHATSAPP] Callback report sent to {wa_to}")
                    except Exception as e:
                        print(f"[WHATSAPP ERROR] {e}")

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
