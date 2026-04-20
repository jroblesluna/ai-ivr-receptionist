import json
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather
import config
import db
from config import twilio_client
import runtime_config
import reports


def _now_local():
    tz_name = runtime_config.get("timezone", "America/Lima")
    try:
        tz = ZoneInfo(tz_name)
        return datetime.now(tz)
    except Exception:
        return datetime.utcnow()


def _normalize_client(name: str) -> str:
    """Lowercase, strip accents and non-alphanumeric chars for fuzzy dedup."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_str.lower())


def _clients_match(a: str, b: str) -> bool:
    """True if two client name strings refer to the same entity."""
    na, nb = _normalize_client(a), _normalize_client(b)
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 8 and shorter in longer
from state import conversation_store, collected_info
from use_case_loader import get_topics, get_active_use_case
from helpers import get_voice, get_gather_language
from prompts import get_system_prompt, get_conversational_prompt
from email_helper import send_report_email

ai_bp = Blueprint("ai", __name__)


def _get_demo_uc(demo_id: str) -> dict | None:
    """Return UC dict for a demo, or None if not found/not a demo."""
    if not demo_id:
        return None
    uc = db.uc_get(demo_id)
    return uc if uc and uc.get("is_demo") else None


def _get_voice_for_uc(lang: str, uc: dict | None) -> str:
    if uc:
        v = uc.get("voice", {}).get(lang, "")
        if v:
            return v
    return get_voice(lang)


@ai_bp.route("/ai-gather", methods=['GET', 'POST'])
def ai_gather():
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "customer_service")
    demo_id  = request.args.get("demo_id", "")
    call_sid = request.form.get("CallSid", request.args.get("CallSid", ""))

    demo_uc = _get_demo_uc(demo_id)
    voice   = _get_voice_for_uc(lang, demo_uc)
    gl      = get_gather_language(lang)

    resp = VoiceResponse()

    # Primera visita: inicializar historial y saludar
    if call_sid and call_sid not in conversation_store:
        caller_from  = request.values.get("From", "")
        caller_profile = db.caller_profile_get(caller_from, demo_id) if demo_id and caller_from else {}

        is_conversational = demo_uc and demo_uc.get("ivr_type") == "conversational"

        if is_conversational:
            system_prompt = get_conversational_prompt(lang, demo_uc, caller_from=caller_from, caller_profile=caller_profile)
        else:
            system_prompt = get_system_prompt(lang, topic, caller_from=caller_from,
                                              caller_profile=caller_profile if demo_id else None)

        conversation_store[call_sid] = [{"role": "system", "content": system_prompt}]
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
            "demo_id":             demo_id or None,
        }

        if is_conversational:
            # Generate the opening greeting via LLM so it uses the full system prompt context
            trigger = "(start conversation)" if lang == "en" else "(iniciar conversación)"
            try:
                _history_for_greeting = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": trigger},
                ]
                _gr_completion = config.openai_client().chat.completions.create(
                    model="gpt-4o-mini",
                    messages=_history_for_greeting,
                    response_format={"type": "json_object"},
                    max_tokens=300,
                )
                _gr_json = json.loads(_gr_completion.choices[0].message.content)
                greeting = _gr_json.get("message") or ""
            except Exception as _gr_err:
                print(f"[AI GREETING ERROR] {_gr_err}")
                greeting = ""
            if not greeting:
                known_name = caller_profile.get("name", "")
                greeting = (
                    f"{'Welcome back, ' + known_name + '!' if known_name else 'Hello!'} "
                    f"Thank you for calling {demo_uc['name']}. How can I help you today?"
                    if lang == "en" else
                    f"Bienvenido{' de nuevo, ' + known_name if known_name else ''} a {demo_uc['name']}. ¿En qué le puedo ayudar?"
                )
            conversation_store[call_sid].append({"role": "user",      "content": trigger})
            conversation_store[call_sid].append({"role": "assistant", "content": greeting})
        else:
            TOPICS = get_topics() if not demo_uc else _get_demo_topics(demo_uc)
            fallback_topic = list(TOPICS.keys())[0] if TOPICS else topic
            topic_data = TOPICS.get(topic) or TOPICS.get(fallback_topic, {})
            lang_data  = topic_data.get(lang) or topic_data.get("en", {})
            greeting   = lang_data.get("greeting", "Hello, how can I help you?")
            conversation_store[call_sid].append({"role": "assistant", "content": greeting})

        resp.say(greeting, voice=voice)

    demo_suffix = f"&demo_id={demo_id}" if demo_id else ""
    gather = Gather(
        input="speech",
        action=f"/ai-respond?lang={lang}&topic={topic}{demo_suffix}",
        method="POST",
        speech_timeout="auto",
        timeout=5,
        language=gl
    )
    resp.append(gather)

    silence = "I'm sorry, I didn't catch that. Please try again." if lang == "en" else "Lo siento, no le escuché. Por favor intente de nuevo."
    resp.say(silence, voice=voice)
    resp.redirect(f"/ai-gather?lang={lang}&topic={topic}{demo_suffix}")
    return str(resp)


def _get_demo_topics(demo_uc: dict) -> dict:
    """Build a TOPICS-compatible dict from a demo use case for greeting lookups."""
    company = demo_uc["name"]
    topics  = {}
    for topic_id, topic_data in demo_uc.get("topics", {}).items():
        topics[topic_id] = {
            "en": {**topic_data.get("en", {}), "meeting_type": topic_data.get("meeting_type", False), "digit": topic_data.get("digit", "")},
            "es": {**topic_data.get("es", {}), "meeting_type": topic_data.get("meeting_type", False), "digit": topic_data.get("digit", "")},
        }
    topics["schedule_callback"] = {
        "en": {"greeting": f"I'm sorry, the team at {company} is not available right now. Let me schedule a callback.", "system_extra": "", "questions": [], "meeting_type": False, "digit": ""},
        "es": {"greeting": f"Lo siento, el equipo de {company} no está disponible. Le agendaremos una rellamada.", "system_extra": "", "questions": [], "meeting_type": False, "digit": ""},
    }
    return topics


@ai_bp.route("/ai-respond", methods=['GET', 'POST'])
def ai_respond():
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "customer_service")
    demo_id  = request.args.get("demo_id", "")
    call_sid = request.form.get("CallSid", "")
    speech   = request.form.get("SpeechResult", "").strip()

    demo_uc     = _get_demo_uc(demo_id)
    voice       = _get_voice_for_uc(lang, demo_uc)
    gl          = get_gather_language(lang)
    demo_suffix = f"&demo_id={demo_id}" if demo_id else ""

    resp = VoiceResponse()

    if not speech:
        silence = "I'm sorry, I didn't catch that. Please try again." if lang == "en" else "Lo siento, no le escuché. Por favor intente de nuevo."
        resp.say(silence, voice=voice)
        resp.redirect(f"/ai-gather?lang={lang}&topic={topic}{demo_suffix}")
        return str(resp)

    # Inicializar si no existe (edge case)
    if call_sid not in conversation_store:
        caller_from    = request.values.get("From", "")
        caller_profile = db.caller_profile_get(caller_from, demo_id) if demo_id and caller_from else {}
        is_conv        = demo_uc and demo_uc.get("ivr_type") == "conversational"
        if is_conv:
            sp = get_conversational_prompt(lang, demo_uc, caller_from=caller_from, caller_profile=caller_profile)
        else:
            sp = get_system_prompt(lang, topic, caller_from=caller_from, caller_profile=caller_profile if demo_id else None)
        conversation_store[call_sid] = [{"role": "system", "content": sp}]
        collected_info[call_sid] = {
            "name": None, "phone": None, "notes": None,
            "topic": topic, "lang": lang, "caller_from": caller_from, "demo_id": demo_id or None,
        }

    history = conversation_store[call_sid]
    history.append({"role": "user", "content": speech})

    # Llamar a OpenAI
    try:
        completion = config.openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=history,
            response_format={"type": "json_object"}
        )
        ai_json        = json.loads(completion.choices[0].message.content)
        message        = ai_json.get("message") or ("One moment please." if lang == "en" else "Un momento por favor.")
        name           = ai_json.get("name") or None
        phone          = ai_json.get("phone") or None
        notes          = ai_json.get("notes") or None
        end_call       = ai_json.get("end_call", False)
        profile_update = ai_json.get("profile_update") or {}
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

    # Actualizar perfil de llamante si es un demo
    _current_demo_id = info.get("demo_id") or demo_id
    if _current_demo_id:
        caller_from_for_profile = info.get("caller_from", "")
        if caller_from_for_profile:
            existing_profile = db.caller_profile_get(caller_from_for_profile, _current_demo_id)
            changed = False
            if name and existing_profile.get("name") != name:
                existing_profile["name"] = name
                changed = True
            if phone and existing_profile.get("phone") != phone:
                existing_profile["phone"] = phone
                changed = True
            if notes and existing_profile.get("last_notes") != notes:
                existing_profile["last_notes"] = notes
                changed = True
            if isinstance(profile_update, dict) and profile_update:
                for k, v in profile_update.items():
                    if isinstance(v, list) and isinstance(existing_profile.get(k), list):
                        existing_list = existing_profile[k]
                        for item in v:
                            if not isinstance(item, dict):
                                continue
                            # Skip incomplete activity entries
                            item_date   = str(item.get("fecha") or item.get("date", "")).strip()
                            item_client = str(item.get("cliente") or item.get("client", "")).strip()
                            item_type   = str(item.get("type", "")).strip()
                            if not item_date or not item_client:
                                continue
                            # Fuzzy dedup: same type + same date + fuzzy-matching client name
                            is_dup = any(
                                str(x.get("type", "")) == item_type
                                and str(x.get("fecha") or x.get("date", "")) == item_date
                                and _clients_match(item_client, str(x.get("cliente") or x.get("client", "")))
                                for x in existing_list if isinstance(x, dict)
                            )
                            if not is_dup:
                                existing_list.append(item)
                        existing_profile[k] = existing_list
                    else:
                        existing_profile[k] = v
                changed = True
            if changed:
                db.caller_profile_set(caller_from_for_profile, _current_demo_id, existing_profile,
                                      updated_at=_now_local().strftime("%Y-%m-%d %H:%M:%S"))

    # Enviar WhatsApp cuando tengamos nombre y teléfono (solo una vez)
    if info["name"] and info["phone"] and not info.get("notified"):
        info["notified"] = True
        collected_info[call_sid] = info
        if _current_demo_id:
            demo_uc_for_label = db.uc_get(_current_demo_id)
            all_topics = _get_demo_topics(demo_uc_for_label) if demo_uc_for_label else get_topics()
        else:
            all_topics = get_topics()
        TOPICS = all_topics
        topic_label = TOPICS.get(topic, {}).get(lang, TOPICS.get(topic, {}).get("en", {})).get("label", topic)
        lines = [
            f"📋 *Nueva consulta* — {_now_local().strftime('%Y-%m-%d %H:%M:%S')}",
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
                msg = twilio_client().messages.create(
                    from_=f"whatsapp:{wa_from}",
                    to=f"whatsapp:{wa_to}",
                    body="\n".join(lines),
                )
                print(f"[WHATSAPP] Pre-screening alert sent to {wa_to} | SID: {msg.sid}")
            except Exception as e:
                print(f"[WHATSAPP ERROR] {e}")

    if end_call:
        resp.say(message, voice=voice)
        # Save pre-existing conversation before overwriting (used in schedule_callback merge)
        prescreening_conv = info.get("conversation") or []
        # Guardar historial antes de limpiar (para el reporte final)
        history_snapshot = conversation_store.pop(call_sid, [])
        info["conversation"] = [m for m in history_snapshot if m["role"] != "system"]
        info["goodbye"] = message
        collected_info[call_sid] = info
        _is_conv_demo = demo_uc and demo_uc.get("ivr_type") == "conversational"
        if _is_conv_demo:
            # Save report and hang up — no human operator for conversational agents
            base_url = request.url_root.rstrip("/")
            conv_history = info.get("conversation") or []
            report_data = {
                "timestamp":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "use_case":               demo_uc.get("name", "") if demo_uc else "",
                "caller_name":            info.get("name") or info.get("caller_from", ""),
                "caller_phone":           info.get("phone") or info.get("caller_from", ""),
                "topic":                  "Conversational Agent",
                "language":               "English" if lang == "en" else "Español",
                "conversation":           conv_history,
                "operator_briefing":      "",
                "transcription":          "",
                "transcription_segments": [],
                "summary":                info.get("notes") or "",
                "goodbye":                info.get("goodbye", ""),
            }
            report_id = reports.save(report_data)
            print(f"[CONV REPORT] {report_id}")
            resp.hangup()
        elif topic != "schedule_callback" and topic != "_conversational" and info.get("name") and info.get("phone"):
            base_url = request.url_root.rstrip("/")
            resp.redirect(f"{base_url}/connect-operator?lang={lang}&caller_sid={call_sid}{demo_suffix}")
        elif topic == "_conversational" and info.get("name") and info.get("phone"):
            base_url = request.url_root.rstrip("/")
            resp.redirect(f"{base_url}/connect-operator?lang={lang}&caller_sid={call_sid}{demo_suffix}")
        elif topic == "schedule_callback":
            preferred  = info.get("notes") or "(no times provided)"
            base_url   = request.url_root.rstrip("/")
            if _current_demo_id:
                uc = db.uc_get(_current_demo_id) or get_active_use_case()
            else:
                uc = get_active_use_case()
            company    = uc.get("name", "")
            TOPICS     = _get_demo_topics(uc) if _current_demo_id else get_topics()
            orig_topic = info.get("topic") or topic
            topic_label = TOPICS.get(orig_topic, {}).get(lang, {}).get("label") or \
                          TOPICS.get(orig_topic, {}).get("en", {}).get("label") or \
                          ("Callback Request" if lang == "en" else "Solicitud de Rellamada")

            # Merge pre-screening conversation + callback scheduling conversation
            callback_conv     = info.get("conversation") or []
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
                        msg = twilio_client().messages.create(
                            from_=f"whatsapp:{wa_from}",
                            to=f"whatsapp:{wa_to}",
                            body=wa_body,
                        )
                        print(f"[WHATSAPP] Callback report sent to {wa_to} | SID: {msg.sid}")
                    except Exception as e:
                        print(f"[WHATSAPP ERROR] {e}")

            resp.hangup()
        else:
            resp.hangup()
    else:
        gather = Gather(
            input="speech",
            action=f"/ai-respond?lang={lang}&topic={topic}{demo_suffix}",
            method="POST",
            speech_timeout="auto",
            timeout=5,
            language=gl
        )
        gather.say(message, voice=voice)
        resp.append(gather)

        silence = "I'm sorry, I didn't catch that." if lang == "en" else "Lo siento, no le escuché."
        resp.say(silence, voice=voice)
        resp.redirect(f"/ai-gather?lang={lang}&topic={topic}{demo_suffix}")

    return str(resp)
