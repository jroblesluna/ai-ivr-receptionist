import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Gather, Connect, Stream
import requests as http_requests
import config
import db
from config import twilio_client
import runtime_config
import reports

logger = logging.getLogger(__name__)

WS_HOST = os.environ.get("WS_HOST", "") or config.SecretsConfig.get("WS_HOST", "")


def _now_local():
    tz_name = runtime_config.get("timezone", "America/Lima").replace(" ", "_")
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        print(f"[TZ] {tz_name} → {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        return now
    except Exception as e:
        print(f"[TZ ERROR] ZoneInfo({tz_name!r}) failed: {e} — falling back to UTC")
        return datetime.now(ZoneInfo("UTC"))


# Field names that carry free-text detail — excluded from dedup identity comparison
_DETAIL_FIELDS = frozenset({
    "detalle", "details", "description", "descripcion",
    "notes", "nota", "notas", "comment", "comentario", "summary", "resumen",
})

# Canonical key map: normalises bilingual (ES/EN) and common synonym field names
# so that {"cliente":"X","fecha":"Y"} and {"client":"X","date":"Y"} are the same item.
_KEY_CANON = {
    # entity / who
    "client": "client", "cliente": "client", "customer": "client", "cliente_nombre": "client",
    # date / when
    "date": "date", "fecha": "date", "fecha_iso": "date", "day": "date", "dia": "date",
    # type / category
    "type": "type", "tipo": "type", "kind": "type", "categoria": "type", "category": "type",
    # product
    "product": "product", "producto": "product", "item": "product", "articulo": "product",
    # quantity
    "quantity": "qty", "cantidad": "qty", "qty": "qty", "amount": "qty", "monto": "qty",
    # status
    "status": "status", "estado": "status", "state": "status",
    # name (person)
    "name": "name", "nombre": "name",
    # detail fields (also in _DETAIL_FIELDS, mapped here for completeness)
    "detail": "detail", "detalle": "detail", "details": "detail",
    "description": "detail", "descripcion": "detail",
    "notes": "detail", "nota": "detail", "notas": "detail",
    "comment": "detail", "comentario": "detail",
    "summary": "detail", "resumen": "detail",
}


def _canon_key(k: str) -> str:
    return _KEY_CANON.get(k.lower(), k.lower())


def _normalize_str(s: str) -> str:
    """Lowercase, strip accents and non-alphanumeric for fuzzy comparison."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_str.lower())


def _values_match(a: str, b: str) -> bool:
    """Exact or fuzzy substring match for identifying field values."""
    na, nb = _normalize_str(a), _normalize_str(b)
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 8 and shorter in longer


def _is_duplicate_item(new_item: dict, existing_list: list) -> bool:
    """
    Cross-call deduplication safety net for profile_update list items.
    Primary prevention of within-call duplicates is the conversation flow (prompt).
    This handles edge cases: same item stored under different language field names.

    Algorithm:
    - Canonicalise field names via _KEY_CANON (ES/EN bilingual normalisation).
    - Exclude free-text detail fields from the identity comparison.
    - Require the same canonical key set to match (exact, not intersection)
      so that two legitimately different activities on the same date/client
      with different types are never mistakenly merged.
    - Use fuzzy value matching for entity name strings.
    """
    def _canon_id(item: dict) -> dict:
        result = {}
        for k, v in item.items():
            ck = _canon_key(k)
            if ck not in _DETAIL_FIELDS and ck != "detail":
                result[ck] = v
        return result

    new_id = _canon_id(new_item)
    if not any(v for v in new_id.values()):
        return True  # empty/meaningless item — skip
    for existing in existing_list:
        if not isinstance(existing, dict):
            continue
        ex_id = _canon_id(existing)
        if set(new_id.keys()) != set(ex_id.keys()):
            continue  # different structure → different record
        if all(_values_match(str(new_id[k]), str(ex_id[k])) for k in new_id):
            return True
    return False


import redis
from session_store import session_store
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


def _check_media_stream_health() -> bool:
    """Check if the Media Stream Server is reachable via its health endpoint.

    Returns True if the server responds with HTTP 200, False otherwise.
    """
    try:
        resp = http_requests.get("http://localhost:8001/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def _build_media_stream_twiml(lang: str, demo_id: str, caller_from: str) -> str:
    """Return TwiML with <Connect><Stream> pointing to the WebSocket server."""
    resp = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"wss://{WS_HOST}/media-stream")
    stream.parameter(name="lang", value=lang)
    stream.parameter(name="demo_id", value=demo_id)
    stream.parameter(name="caller_from", value=caller_from)
    connect.append(stream)
    resp.append(connect)
    return str(resp)


@ai_bp.route("/ai-gather", methods=['GET', 'POST'])
def ai_gather():
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "customer_service")
    demo_id  = request.args.get("demo_id", "")
    call_sid = request.form.get("CallSid", request.args.get("CallSid", ""))

    logger.info(
        "[AI-GATHER] START call_sid=%s lang=%s topic=%s demo_id=%s",
        call_sid, lang, topic, demo_id,
    )

    demo_uc = _get_demo_uc(demo_id)
    voice   = _get_voice_for_uc(lang, demo_uc)
    gl      = get_gather_language(lang)

    logger.info(
        "[AI-GATHER] demo_uc=%s ivr_type=%s voice=%s",
        demo_uc.get("name") if demo_uc else None,
        demo_uc.get("ivr_type") if demo_uc else None,
        voice,
    )

    resp = VoiceResponse()

    try:
        # Primera visita: inicializar historial y saludar
        if call_sid and not session_store.has_conversation(call_sid):
            caller_from  = request.values.get("From", "")
            caller_profile = db.caller_profile_get(caller_from, demo_id) if demo_id and caller_from else {}

            is_conversational = demo_uc and demo_uc.get("ivr_type") == "conversational"

            if is_conversational:
                system_prompt = get_conversational_prompt(lang, demo_uc, caller_from=caller_from, caller_profile=caller_profile)
            else:
                system_prompt = get_system_prompt(lang, topic, caller_from=caller_from,
                                                  caller_profile=caller_profile if demo_id else None)

            session_store.set_conversation(call_sid, [{"role": "system", "content": system_prompt}])
            prior = session_store.get_collected_info(call_sid)
            session_store.set_collected_info(call_sid, {
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
            })

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
                conversation = session_store.get_conversation(call_sid)
                conversation.append({"role": "user",      "content": trigger})
                conversation.append({"role": "assistant", "content": greeting})
                session_store.set_conversation(call_sid, conversation)
            else:
                TOPICS = get_topics() if not demo_uc else _get_demo_topics(demo_uc)
                fallback_topic = list(TOPICS.keys())[0] if TOPICS else topic
                topic_data = TOPICS.get(topic) or TOPICS.get(fallback_topic, {})
                lang_data  = topic_data.get(lang) or topic_data.get("en", {})
                greeting   = lang_data.get("greeting", "Hello, how can I help you?")
                conversation = session_store.get_conversation(call_sid)
                conversation.append({"role": "assistant", "content": greeting})
                session_store.set_conversation(call_sid, conversation)

            resp.say(greeting, voice=voice)

        # For conversational demos, use <Connect><Stream> instead of <Gather speech>
        is_conversational_demo = demo_uc and demo_uc.get("ivr_type") == "conversational"
        logger.info(
            "[AI-GATHER] is_conversational_demo=%s call_sid=%s",
            is_conversational_demo, call_sid,
        )
        if is_conversational_demo:
            caller_from = request.values.get("From", "")
            health_ok = _check_media_stream_health()
            logger.info(
                "[AI-GATHER] Media Stream health_ok=%s WS_HOST=%s caller_from=%s",
                health_ok, WS_HOST, caller_from,
            )
            if health_ok:
                twiml = _build_media_stream_twiml(
                    lang=lang,
                    demo_id=demo_id,
                    caller_from=caller_from,
                )
                logger.info("[AI-GATHER] Returning <Connect><Stream> TwiML: %s", twiml[:200])
                return twiml
            else:
                logger.warning(
                    "Media Stream Server unreachable; falling back to <Gather speech> "
                    "for call_sid=%s, demo_id=%s",
                    call_sid, demo_id,
                )

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
        logger.info("[AI-GATHER] Returning <Gather speech> TwiML call_sid=%s", call_sid)
        return str(resp)
    except redis.RedisError as e:
        logger.error("[AI-GATHER] Redis error call_sid=%s error=%s", call_sid, e)
        resp = VoiceResponse()
        resp.say("We are experiencing technical difficulties. Please try again later.", voice=voice)
        resp.hangup()
        return str(resp)
    except Exception as e:
        logger.error(
            "[AI-GATHER] UNHANDLED EXCEPTION call_sid=%s demo_id=%s error=%s",
            call_sid, demo_id, e, exc_info=True,
        )
        resp = VoiceResponse()
        resp.say("We are experiencing technical difficulties. Please try again later.", voice=voice)
        resp.hangup()
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

    try:
        # Inicializar si no existe (edge case)
        if not session_store.has_conversation(call_sid):
            caller_from    = request.values.get("From", "")
            caller_profile = db.caller_profile_get(caller_from, demo_id) if demo_id and caller_from else {}
            is_conv        = demo_uc and demo_uc.get("ivr_type") == "conversational"
            if is_conv:
                sp = get_conversational_prompt(lang, demo_uc, caller_from=caller_from, caller_profile=caller_profile)
            else:
                sp = get_system_prompt(lang, topic, caller_from=caller_from, caller_profile=caller_profile if demo_id else None)
            session_store.set_conversation(call_sid, [{"role": "system", "content": sp}])
            session_store.set_collected_info(call_sid, {
                "name": None, "phone": None, "notes": None,
                "topic": topic, "lang": lang, "caller_from": caller_from, "demo_id": demo_id or None,
            })

        history = session_store.get_conversation(call_sid)
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
        session_store.set_conversation(call_sid, history)

        # Actualizar info recolectada
        info = session_store.get_collected_info(call_sid)
        if name:
            info["name"] = name
        if phone:
            info["phone"] = phone
        if notes:
            info["notes"] = notes
        session_store.set_collected_info(call_sid, info)

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
                                if not _is_duplicate_item(item, existing_list):
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
            session_store.set_collected_info(call_sid, info)
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
            history_snapshot = session_store.pop_conversation(call_sid)
            info["conversation"] = [m for m in history_snapshot if m["role"] != "system"]
            info["goodbye"] = message
            session_store.set_collected_info(call_sid, info)
            _is_conv_demo = demo_uc and demo_uc.get("ivr_type") == "conversational"
            if _is_conv_demo:
                # Save report and hang up — no human operator for conversational agents
                base_url = request.url_root.rstrip("/")
                conv_history = info.get("conversation") or []
                report_data = {
                    "timestamp":              _now_local().strftime("%Y-%m-%d %H:%M:%S"),
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
                    "goodbye":               info.get("goodbye", ""),
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
                    "timestamp":              _now_local().strftime("%Y-%m-%d %H:%M:%S"),
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
    except redis.RedisError:
        resp = VoiceResponse()
        resp.say("We are experiencing technical difficulties. Please try again later.", voice=voice)
        resp.hangup()
        return str(resp)
