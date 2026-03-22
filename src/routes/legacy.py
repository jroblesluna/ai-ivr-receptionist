import uuid
from flask import Blueprint, request
from twilio.twiml.voice_response import VoiceResponse, Dial
from config import ACCOUNT_SID, AUTH_TOKEN, TWILIO_FROM, FORWARD_TO, twilio_client
from state import outbound_calls, failed_rooms
from helpers import get_voice

legacy_bp = Blueprint("legacy", __name__)

HOLD_EN = "Thank you! Please hold, someone will be with you shortly."
HOLD_ES = "¡Gracias! En un momento le atenderemos, por favor espere en línea."


@legacy_bp.route("/forward", methods=['GET', 'POST'])
def forward():
    lang       = request.args.get("lang", "en")
    topic      = request.args.get("topic", "meeting")
    caller_sid = request.form.get("CallSid", "")
    voice      = get_voice(lang)
    hold_msg   = HOLD_EN if lang == "en" else HOLD_ES
    room       = f"room-{uuid.uuid4().hex}"
    base_url   = request.url_root.rstrip("/")

    resp = VoiceResponse()
    resp.say(hold_msg, voice=voice)

    # Caller espera en conferencia escuchando wait1 en loop
    # action captura cuando la conferencia termina (agente colgó tras contestar)
    dial = Dial(action=f"/conference-ended?lang={lang}&topic={topic}", method="POST")
    dial.conference(
        room,
        wait_url=f"{base_url}/hold-music/1?room={room}&lang={lang}&topic={topic}",
        wait_method="GET",
        start_conference_on_enter=False,
        end_conference_on_exit=True,
        beep=False,
        status_callback=f"{base_url}/conference-status?room={room}",
        status_callback_event=["end"],
        status_callback_method="POST",
    )
    resp.append(dial)

    # Llamar al agente en paralelo
    outbound = twilio_client().calls.create(
        to=FORWARD_TO,
        from_=TWILIO_FROM,
        twiml=(
            f'<Response><Dial>'
            f'<Conference startConferenceOnEnter="true" endConferenceOnExit="true" beep="false">'
            f'{room}'
            f'</Conference></Dial></Response>'
        ),
        status_callback=f"{base_url}/agent-status?room={room}&lang={lang}&topic={topic}&caller_sid={caller_sid}",
        status_callback_method="POST",
        status_callback_event=["completed"],
    )
    outbound_calls[room] = outbound.sid

    return str(resp)


@legacy_bp.route("/conference-ended", methods=['GET', 'POST'])
def conference_ended():
    """El <Dial> del caller completó (conferencia terminó — agente colgó tras contestar)."""
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "meeting")
    base_url = request.url_root.rstrip("/")
    print(f"[CONFERENCE-ENDED] lang={lang!r} topic={topic!r}")
    resp = VoiceResponse()
    resp.redirect(f"{base_url}/ai-gather?lang={lang}&topic={topic}")
    return str(resp)


@legacy_bp.route("/conference-status", methods=['GET', 'POST'])
def conference_status():
    """Caller colgó — cancela la llamada saliente al agente."""
    room         = request.values.get("room", "")
    outbound_sid = outbound_calls.pop(room, None)
    failed_rooms.discard(room)
    if outbound_sid:
        try:
            twilio_client().calls(outbound_sid).update(status="canceled")
        except Exception:
            pass
    return ("", 204)


@legacy_bp.route("/agent-status", methods=['GET', 'POST'])
def agent_status():
    """Llamada al agente terminó — redirigir al caller a la IA en cualquier caso."""
    call_status = request.values.get("CallStatus", "")
    room        = request.values.get("room", "")
    caller_sid  = request.values.get("caller_sid", "")
    lang        = request.values.get("lang", "en")
    topic       = request.values.get("topic", "meeting")
    base_url    = request.url_root.rstrip("/")

    print(f"[AGENT-STATUS] CallStatus={call_status!r} room={room!r} caller_sid={caller_sid!r}")

    outbound_calls.pop(room, None)

    terminal_statuses = {"no-answer", "busy", "failed", "canceled", "completed"}
    if call_status in terminal_statuses:
        # Mecanismo 1: marcar room para que waitUrl redirija en el próximo ciclo
        if room:
            failed_rooms.add(room)

        # Mecanismo 2: redirigir al caller inmediatamente via REST API
        if caller_sid:
            try:
                twilio_client().calls(caller_sid).update(
                    url=f"{base_url}/ai-gather?lang={lang}&topic={topic}",
                    method="POST",
                )
                print(f"[AGENT-STATUS] REST redirect OK → caller_sid={caller_sid!r}")
            except Exception as e:
                print(f"[AGENT-STATUS] REST redirect failed: {e}")

    return ("", 204)


@legacy_bp.route("/hold-music/<int:num>", methods=['GET', 'POST'])
def hold_music(num):
    room  = request.args.get("room", "")
    lang  = request.args.get("lang", "en")
    topic = request.args.get("topic", "meeting")

    # Agente no contestó → sacar al caller de la conferencia hacia la IA
    if room and room in failed_rooms:
        failed_rooms.discard(room)
        base_url = request.url_root.rstrip("/")
        resp = VoiceResponse()
        resp.redirect(f"{base_url}/ai-gather?lang={lang}&topic={topic}")
        return str(resp)

    resp = VoiceResponse()
    resp.play(request.url_root + "wait-music.wav", loop=1)
    return str(resp)
