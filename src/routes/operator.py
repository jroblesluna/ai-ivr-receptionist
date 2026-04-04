import uuid
import io
from datetime import datetime
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Dial
import runtime_config
import reports
from config import ACCOUNT_SID, AUTH_TOKEN, openai_client, twilio_client
from state import collected_info, outbound_calls, failed_rooms, briefed_rooms
from use_case_loader import get_topics
from helpers import get_voice
from use_case_loader import get_company_name, get_active_use_case
from email_helper import send_report_email

operator_bp = Blueprint("operator", __name__)


@operator_bp.route("/connect-operator", methods=['GET', 'POST'])
def connect_operator():
    lang       = request.values.get("lang", "en")
    caller_sid = request.values.get("caller_sid", request.form.get("CallSid", ""))
    room       = f"room-{uuid.uuid4().hex}"
    base_url   = request.url_root.rstrip("/")

    resp = VoiceResponse()

    # Caller espera en conferencia con música; se graba para resumen posterior
    dial = Dial(
        action=f"{base_url}/meeting-ended?lang={lang}",
        method="POST",
    )
    dial.conference(
        room,
        wait_url=f"{base_url}/operator-hold-music?room={room}&lang={lang}",
        wait_method="GET",
        start_conference_on_enter=False,
        end_conference_on_exit=True,
        beep=False,
        record="record-from-start",
        recording_channels="dual",
        recording_status_callback=f"{base_url}/recording-ready?caller_sid={caller_sid}&lang={lang}",
        recording_status_callback_method="POST",
    )
    resp.append(dial)
    print(f"[TWIML] connect-operator:\n{str(resp)}")

    # Llamar al operador; cuando conteste, escucha el briefing y luego se une a la conferencia
    FORWARD_TO  = runtime_config.get("forward_to")  or ""
    TWILIO_FROM = runtime_config.get("twilio_from") or ""
    print(f"[CONNECT-OPERATOR] caller_sid={caller_sid!r} room={room!r} to={FORWARD_TO!r} from={TWILIO_FROM!r}")
    try:
        outbound = twilio_client().calls.create(
            to=FORWARD_TO,
            from_=TWILIO_FROM,
            url=f"{base_url}/operator-briefing?caller_sid={caller_sid}&room={room}&lang={lang}",
            timeout=25,
            machine_detection="Enable",
            status_callback=f"{base_url}/operator-status?room={room}&caller_sid={caller_sid}&lang={lang}&attempt=1",
            status_callback_method="POST",
            status_callback_event=["completed"],
        )
        outbound_calls[room] = outbound.sid
        print(f"[CONNECT-OPERATOR] Outbound call created: {outbound.sid}")
    except Exception as e:
        print(f"[CONNECT-OPERATOR ERROR] Failed to create outbound call: {e}")
    return str(resp)


@operator_bp.route("/operator-hold-music", methods=['GET', 'POST'])
def operator_hold_music():
    room  = request.values.get("room", "")
    lang  = request.values.get("lang", "en")
    base_url = request.url_root.rstrip("/")

    if room and room in failed_rooms:
        failed_rooms.discard(room)
        resp = VoiceResponse()
        resp.redirect(f"{base_url}/no-availability?lang={lang}")
        return str(resp)

    use_case_id = runtime_config.get("use_case_id") or ""
    uc    = get_active_use_case()
    voice = get_voice(lang)
    url   = uc.get("url", "")

    if lang == "en":
        msg = "All our agents are currently busy." + (f" You can also visit us at {url}." if url else "") + " Please hold on for a moment."
    else:
        msg = "Todos nuestros agentes están ocupados en este momento." + (f" También puede visitarnos en {url}." if url else "") + " Por favor, espere un momento."

    resp = VoiceResponse()
    resp.play(request.url_root + f"wait-music-{use_case_id}.wav", loop=1)
    resp.say(msg, voice=voice)
    resp.redirect(f"{base_url}/operator-hold-music?room={room}&lang={lang}")
    return str(resp)


@operator_bp.route("/operator-briefing", methods=['GET', 'POST'])
def operator_briefing():
    """TwiML para el operador: escucha datos del caller, luego se une a la conferencia."""
    caller_sid = request.values.get("caller_sid", "")
    room       = request.values.get("room", "")
    lang       = request.values.get("lang", "en")
    voice      = get_voice(lang)

    # Si contestó una máquina/contestadora, colgar inmediatamente sin unirse a la conferencia
    answered_by = request.values.get("AnsweredBy", "")
    if answered_by and "machine" in answered_by.lower():
        print(f"[OPERATOR-BRIEFING] Answering machine detected ({answered_by}), hanging up")
        resp = VoiceResponse()
        resp.hangup()
        return str(resp)

    # El operador contestó → marcar room para que operator-status no lo trate como no-answer
    if room:
        briefed_rooms.add(room)

    info   = collected_info.get(caller_sid, {})
    name   = info.get("name") or "Unknown"
    phone  = info.get("phone") or "Unknown"
    notes  = info.get("notes") or ""
    topic  = info.get("topic", "")
    topic_label = get_topics().get(topic, {}).get(lang, {}).get("label", topic)

    if lang == "en":
        briefing = f"Incoming pre-screened call. Topic: {topic_label}. Caller name: {name}. Callback number: {phone}."
        if notes:
            briefing += f" Pre-screening notes: {notes}."
        briefing += " Connecting now."
    else:
        briefing = f"Llamada preseleccionada entrante. Tema: {topic_label}. Nombre: {name}. Número de contacto: {phone}."
        if notes:
            briefing += f" Notas de preselección: {notes}."
        briefing += " Conectando ahora."

    # Guardar briefing para el reporte final
    if caller_sid and caller_sid in collected_info:
        collected_info[caller_sid]["operator_briefing"] = briefing

    resp = VoiceResponse()
    resp.say(briefing, voice=voice)

    dial = Dial()
    dial.conference(
        room,
        start_conference_on_enter=True,
        end_conference_on_exit=True,
        beep=False,
    )
    resp.append(dial)
    return str(resp)


@operator_bp.route("/operator-status", methods=['GET', 'POST'])
def operator_status():
    """Callback cuando la llamada al operador termina."""
    call_status = request.values.get("CallStatus", "")
    room        = request.values.get("room", "")
    caller_sid  = request.values.get("caller_sid", "")
    lang        = request.values.get("lang", "en")
    attempt     = int(request.values.get("attempt", 1))
    base_url    = request.url_root.rstrip("/")

    print(f"[OPERATOR-STATUS] CallStatus={call_status!r} room={room!r} attempt={attempt}")

    outbound_calls.pop(room, None)

    # "completed" = operador rechazó/canceló antes de unirse a la conferencia
    # Si briefed_rooms contiene el room, el operador SÍ contestó → no redirigir
    operator_answered = room in briefed_rooms
    briefed_rooms.discard(room)

    no_answer_statuses = {"no-answer", "busy", "failed", "canceled"}
    is_no_answer = call_status in no_answer_statuses or (call_status == "completed" and not operator_answered)

    print(f"[OPERATOR-STATUS] CallStatus={call_status!r} operator_answered={operator_answered} is_no_answer={is_no_answer}")

    if is_no_answer:
        if attempt < 5:
            # Reintentar: el caller sigue esperando en la conferencia
            new_attempt = attempt + 1
            FORWARD_TO  = runtime_config.get("forward_to")  or ""
            TWILIO_FROM = runtime_config.get("twilio_from") or ""
            print(f"[OPERATOR-STATUS] Retrying attempt {new_attempt}/5 to {FORWARD_TO!r}")
            try:
                outbound = twilio_client().calls.create(
                    to=FORWARD_TO,
                    from_=TWILIO_FROM,
                    url=f"{base_url}/operator-briefing?caller_sid={caller_sid}&room={room}&lang={lang}",
                    timeout=25,
                    machine_detection="Enable",
                    status_callback=f"{base_url}/operator-status?room={room}&caller_sid={caller_sid}&lang={lang}&attempt={new_attempt}",
                    status_callback_method="POST",
                    status_callback_event=["completed"],
                )
                outbound_calls[room] = outbound.sid
                print(f"[OPERATOR-STATUS] Retry call created: {outbound.sid}")
            except Exception as e:
                print(f"[OPERATOR-STATUS] Retry call failed: {e}")
                failed_rooms.add(room)
        else:
            # 5 intentos agotados → redirigir al caller a no-availability
            print(f"[OPERATOR-STATUS] Max retries reached, redirecting caller to no-availability")
            if room:
                failed_rooms.add(room)
            if caller_sid:
                try:
                    twilio_client().calls(caller_sid).update(
                        url=f"{base_url}/no-availability?lang={lang}",
                        method="POST",
                    )
                    print(f"[OPERATOR-STATUS] Redirected caller to no-availability")
                except Exception as e:
                    print(f"[OPERATOR-STATUS] REST redirect failed: {e}")

    return ("", 204)


@operator_bp.route("/no-availability", methods=['GET', 'POST'])
def no_availability():
    """Operador no disponible — iniciar flujo de IA para agendar rellamada."""
    lang     = request.values.get("lang", "en")
    base_url = request.url_root.rstrip("/")
    resp = VoiceResponse()
    resp.redirect(f"{base_url}/ai-gather?lang={lang}&topic=schedule_callback")
    return str(resp)


@operator_bp.route("/meeting-ended", methods=['GET', 'POST'])
def meeting_ended():
    """Dial action cuando la conferencia termina (operador colgó tras la llamada)."""
    lang  = request.values.get("lang", "en")
    voice = get_voice(lang)

    company = get_company_name()
    msg = f"Thank you for calling {company}. Have a great day!" if lang == "en" else f"Gracias por llamar a {company}. ¡Que tenga un excelente día!"

    resp = VoiceResponse()
    resp.say(msg, voice=voice)
    resp.hangup()
    return str(resp)


@operator_bp.route("/recording-ready", methods=['GET', 'POST'])
def recording_ready():
    """Twilio llama aquí cuando la grabación de la conferencia está lista."""
    recording_url = request.values.get("RecordingUrl", "")
    caller_sid    = request.values.get("caller_sid", "")
    lang          = request.values.get("lang", "en")

    if not recording_url:
        return ("", 204)

    print(f"[RECORDING] Procesando grabación: {recording_url}")

    try:
        # Descargar el audio
        import requests as req
        audio_resp = req.get(
            recording_url + ".mp3",
            auth=(ACCOUNT_SID, AUTH_TOKEN),
            timeout=30,
        )
        audio_bytes = audio_resp.content

        # Transcribir con diarización si hay 2 canales, mono si no
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))

        def transcribe_channel(audio_seg, filename):
            buf = io.BytesIO()
            audio_seg.export(buf, format="mp3")
            buf.seek(0)
            return openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=(filename, buf, "audio/mpeg"),
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        print(f"[RECORDING] Channels: {audio.channels}")
        transcription_segments = []
        if audio.channels == 2:
            ch = audio.split_to_mono()
            caller_t   = transcribe_channel(ch[0], "caller.mp3")
            operator_t = transcribe_channel(ch[1], "operator.mp3")
            transcription_segments = sorted(
                [{"speaker": "CALLER",   "start": s.start, "text": s.text.strip()} for s in caller_t.segments if s.text.strip()] +
                [{"speaker": "OPERATOR", "start": s.start, "text": s.text.strip()} for s in operator_t.segments if s.text.strip()],
                key=lambda s: s["start"]
            )
            text = "\n".join(f"[{s['speaker']}]: {s['text']}" for s in transcription_segments)
        else:
            result = transcribe_channel(audio, "recording.mp3")
            text = result.text

        # Resumir con GPT
        info    = collected_info.get(caller_sid, {})
        company = get_company_name()
        summary_prompt = (
            f"The following is a transcript of a business call between a customer and an operator at {company}.\n"
            f"Customer info: Name={info.get('name')}, Phone={info.get('phone')}, Notes={info.get('notes')}.\n\n"
            f"Transcript:\n{text}\n\n"
            f"Please provide a concise summary of the conversation including: main topics discussed, "
            f"agreements or next steps, and any important details."
        ) if lang == "en" else (
            f"La siguiente es la transcripción de una llamada de negocios entre un cliente y un asesor de {company}.\n"
            f"Datos del cliente: Nombre={info.get('name')}, Teléfono={info.get('phone')}, Notas={info.get('notes')}.\n\n"
            f"Transcripción:\n{text}\n\n"
            f"Por favor proporciona un resumen conciso de la conversación incluyendo: temas principales, "
            f"acuerdos o próximos pasos, y detalles importantes."
        )

        summary_resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": summary_prompt}],
        )
        summary = summary_resp.choices[0].message.content

        W = 60
        topic_label = get_topics().get(info.get("topic",""), {}).get(lang, {}).get("label", info.get("topic",""))

        print(f"\n{'='*W}")
        print(f"  FULL CALL REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Caller    : {info.get('name')} / {info.get('phone')}")
        print(f"  Topic     : {topic_label}")
        print(f"  Language  : {'English' if lang == 'en' else 'Español'}")
        print(f"{'='*W}")

        # ── 1. IA ↔ User conversation ─────────────────────────
        print(f"\n{'─'*W}")
        print("  [1] AI ↔ CALLER CONVERSATION")
        print(f"{'─'*W}")
        for m in info.get("conversation", []):
            role = "AI  " if m["role"] == "assistant" else "USER"
            print(f"  {role}: {m['content']}")

        # ── 2. IA → Operator briefing ──────────────────────────
        print(f"\n{'─'*W}")
        print("  [2] AI → OPERATOR BRIEFING")
        print(f"{'─'*W}")
        print(f"  {info.get('operator_briefing', '(no briefing recorded)')}")

        # ── 3. User ↔ Operator (Whisper transcription) ─────────
        print(f"\n{'─'*W}")
        print("  [3] CALLER ↔ OPERATOR TRANSCRIPTION (Whisper)")
        print(f"{'─'*W}")
        print(f"  {text}")

        # ── 4. GPT Summary ─────────────────────────────────────
        print(f"\n{'─'*W}")
        print("  [4] GPT SUMMARY")
        print(f"{'─'*W}")
        print(f"  {summary}")

        # ── 5. Goodbye message ─────────────────────────────────
        print(f"\n{'─'*W}")
        print("  [5] GOODBYE MESSAGE (said to caller)")
        print(f"{'─'*W}")
        print(f"  {info.get('goodbye', '(not recorded)')}")

        print(f"\n{'='*W}\n")

        # ── Save report to JSON ────────────────────────────────
        report_data = {
            "timestamp":              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "use_case":               get_company_name(),
            "caller_name":            info.get("name"),
            "caller_phone":           info.get("phone"),
            "topic":                  topic_label,
            "language":               "English" if lang == "en" else "Español",
            "conversation":           info.get("conversation", []),
            "operator_briefing":      info.get("operator_briefing", ""),
            "transcription":          text,
            "transcription_segments": transcription_segments,
            "summary":                summary,
            "goodbye":                info.get("goodbye", ""),
        }
        report_id  = reports.save(report_data)
        base_url   = request.url_root.rstrip("/")
        report_url = f"{base_url}/report/{report_id}"
        print(f"[REPORT] Saved: {report_url}")

        # ── Email — metadata + link ────────────────────────────
        email_body = "\n".join([
            f"New call report from {get_company_name()}",
            f"",
            f"Caller   : {info.get('name', 'Unknown')} / {info.get('phone', '—')}",
            f"Topic    : {topic_label}",
            f"Language : {'English' if lang == 'en' else 'Español'}",
            f"Time     : {report_data['timestamp']}",
            f"",
            f"View full report:",
            f"{report_url}",
        ])
        send_report_email(
            subject=f"[IVR] {info.get('name', 'Unknown')} / {topic_label}",
            body=email_body,
        )

        # ── WhatsApp — metadata + link ─────────────────────────
        if runtime_config.get("notify_whatsapp") == "1":
            wa_from = runtime_config.get("whatsapp_from") or ""
            wa_to   = runtime_config.get("whatsapp_to")   or ""
            if wa_from and wa_to:
                wa_body = "\n".join([
                    f"📋 *New call report* — {report_data['timestamp']}",
                    f"🏢 {get_company_name()}",
                    f"👤 {info.get('name', 'Unknown')} / {info.get('phone', '—')}",
                    f"📌 {topic_label} · {'English' if lang == 'en' else 'Español'}",
                    f"",
                    f"🔗 {report_url}",
                ])
                try:
                    twilio_client().messages.create(
                        from_=f"whatsapp:{wa_from}",
                        to=f"whatsapp:{wa_to}",
                        body=wa_body,
                    )
                    print(f"[WHATSAPP] Report link sent to {wa_to}")
                except Exception as e:
                    print(f"[WHATSAPP ERROR] {e}")

    except Exception as e:
        print(f"[RECORDING ERROR] {e}")

    return ("", 204)
