import os
import uuid
import json
from datetime import datetime
from flask import Flask, request, send_from_directory
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Dial
from openai import OpenAI

app = Flask(__name__)

ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN",  "")
TWILIO_FROM = os.environ.get("TWILIO_NUMBER",      "")
FORWARD_TO  = os.environ.get("FORWARD_TO",         "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
openai_client  = OpenAI(api_key=OPENAI_API_KEY)

HOLD_EN = "Thank you! Please hold, someone will be with you shortly."
HOLD_ES = "¡Gracias! En un momento le atenderemos, por favor espere en línea."

# ── Topic definitions ─────────────────────────────────────────────────────────

TOPICS = {
    "meeting": {
        "en": {
            "label": "Meeting Scheduling",
            "greeting": (
                "Hi! I'm the Robles AI scheduling assistant. "
                "I'll get your information so our team can connect with you right away. "
                "Could I start with your name?"
            ),
            "system_extra": (
                "The caller wants to schedule a meeting with our team. "
                "Your only job is: (1) ask for their full name, "
                "(2) confirm whether the number they called from is their best callback number, "
                "or ask for a different one if they prefer. "
                "Do NOT ask for date, time, or topic of the meeting — the human team will handle that directly."
            ),
        },
        "es": {
            "label": "Agendado de Reuniones",
            "greeting": (
                "¡Hola! Soy el asistente de agendado de Robles AI. "
                "Tomaré sus datos para que nuestro equipo pueda contactarle de inmediato. "
                "¿Podría comenzar diciéndome su nombre?"
            ),
            "system_extra": (
                "El llamante desea agendar una reunión con nuestro equipo. "
                "Su única tarea es: (1) preguntar su nombre completo, "
                "(2) confirmar si el número desde el que llama es el mejor número para devolverle la llamada, "
                "o pedir uno diferente si lo prefiere. "
                "NO pregunte por fecha, hora ni tema de la reunión — el equipo humano coordinará eso directamente."
            ),
        },
    },
    "ai_ml": {
        "en": {
            "label": "AI & Machine Learning Services",
            "greeting": (
                "Hi! I'm the Robles AI pre-screening assistant for Artificial Intelligence and Machine Learning services. "
                "I'll collect some quick information so I can connect you with the right specialist on our team. "
                "Could you please tell me your name?"
            ),
            "system_extra": (
                "The caller is interested in AI and Machine Learning services. "
                "You are collecting information to connect them directly with a human specialist. "
                "After getting their name and confirming their callback number, ask these 3 questions one at a time:\n"
                "1. What specific AI or Machine Learning challenge, use case, or project are you looking to address?\n"
                "2. What industry or sector does your business operate in?\n"
                "3. Do you currently have any data infrastructure, datasets, or existing AI systems in place?"
            ),
        },
        "es": {
            "label": "Servicios de IA y Machine Learning",
            "greeting": (
                "¡Hola! Soy el asistente de preselección de Robles AI para servicios de Inteligencia Artificial y Machine Learning. "
                "Recopilaré algunos datos para conectarle con el especialista correcto de nuestro equipo. "
                "¿Podría decirme su nombre?"
            ),
            "system_extra": (
                "El llamante está interesado en servicios de IA y Machine Learning. "
                "Está recopilando información para conectarle directamente con un especialista humano. "
                "Después de obtener su nombre y confirmar el número de contacto, haga estas 3 preguntas una a la vez:\n"
                "1. ¿Cuál es el reto, caso de uso o proyecto de IA o Machine Learning que desea abordar?\n"
                "2. ¿En qué industria o sector opera su empresa?\n"
                "3. ¿Cuenta actualmente con infraestructura de datos, datasets o sistemas de IA existentes?"
            ),
        },
    },
    "computer_vision": {
        "en": {
            "label": "Computer Vision Services",
            "greeting": (
                "Hi! I'm the Robles AI pre-screening assistant for Computer Vision services. "
                "I'll collect some quick information so I can connect you with the right specialist on our team. "
                "Could you please tell me your name?"
            ),
            "system_extra": (
                "The caller is interested in Computer Vision services. "
                "You are collecting information to connect them directly with a human specialist. "
                "After getting their name and confirming their callback number, ask these 3 questions one at a time:\n"
                "1. What type of visual input will the system process — images, video, or live camera feeds?\n"
                "2. What is the main objective — object detection, image classification, facial recognition, video analysis, or something else?\n"
                "3. Approximately what scale does this need to operate at — how many images or video streams per day?"
            ),
        },
        "es": {
            "label": "Servicios de Visión por Computadora",
            "greeting": (
                "¡Hola! Soy el asistente de preselección de Robles AI para servicios de Visión por Computadora. "
                "Recopilaré algunos datos para conectarle con el especialista correcto de nuestro equipo. "
                "¿Podría decirme su nombre?"
            ),
            "system_extra": (
                "El llamante está interesado en servicios de Visión por Computadora. "
                "Está recopilando información para conectarle directamente con un especialista humano. "
                "Después de obtener su nombre y confirmar el número de contacto, haga estas 3 preguntas una a la vez:\n"
                "1. ¿Qué tipo de entrada visual procesará el sistema — imágenes, video o cámaras en tiempo real?\n"
                "2. ¿Cuál es el objetivo principal — detección de objetos, clasificación de imágenes, reconocimiento facial, análisis de video u otro?\n"
                "3. ¿A qué escala necesita operar la solución — aproximadamente cuántas imágenes o transmisiones de video por día?"
            ),
        },
    },
    "customer_service": {
        "en": {
            "label": "Customer Service",
            "greeting": (
                "Hi! I'm the Robles AI pre-screening assistant for Customer Service. "
                "I'll collect some quick information so I can connect you with the right agent on our team. "
                "Could you please tell me your name?"
            ),
            "system_extra": (
                "The caller needs customer service support. "
                "You are collecting information to connect them directly with a human agent. "
                "After getting their name and confirming their callback number, ask these 3 questions one at a time:\n"
                "1. Which product or service is your inquiry related to?\n"
                "2. Can you briefly describe the issue or problem you are experiencing?\n"
                "3. Is this an urgent issue currently affecting your operations, or is it a general inquiry?"
            ),
        },
        "es": {
            "label": "Servicio al Cliente",
            "greeting": (
                "¡Hola! Soy el asistente de preselección de Robles AI para Servicio al Cliente. "
                "Recopilaré algunos datos para conectarle con el agente correcto de nuestro equipo. "
                "¿Podría decirme su nombre?"
            ),
            "system_extra": (
                "El llamante necesita soporte de servicio al cliente. "
                "Está recopilando información para conectarle directamente con un agente humano. "
                "Después de obtener su nombre y confirmar el número de contacto, haga estas 3 preguntas una a la vez:\n"
                "1. ¿Con cuál producto o servicio está relacionada su consulta?\n"
                "2. ¿Podría describir brevemente el problema o inconveniente que está experimentando?\n"
                "3. ¿Es un problema urgente que está afectando sus operaciones, o es una consulta general?"
            ),
        },
    },
    "schedule_callback": {
        "en": {
            "label": "Schedule Callback",
            "greeting": (
                "I'm sorry, our team is not available at this moment. "
                "I'd like to schedule a callback for you. "
                "Could you tell me at least one preferred date and time for us to call you back?"
            ),
            "system_extra": (
                "The caller was trying to schedule a meeting but no one is available right now. "
                "Your job is to collect at least one preferred date and time for a callback. "
                "Let the caller know they can provide multiple options if they'd like. "
                "Once you have at least one preferred time, confirm the options, "
                "let them know the team will do their best to call back at one of those times, and say goodbye."
            ),
        },
        "es": {
            "label": "Agendar Rellamada",
            "greeting": (
                "Lo sentimos, nuestro equipo no está disponible en este momento. "
                "Me gustaría agendar una rellamada para usted. "
                "¿Podría indicarme al menos una fecha y hora de su preferencia para que le llamemos?"
            ),
            "system_extra": (
                "El llamante intentaba agendar una reunión pero no hay nadie disponible en este momento. "
                "Su tarea es recopilar al menos una fecha y hora preferida para una rellamada. "
                "Indíquele que puede dar varias opciones si lo desea. "
                "Una vez que tenga al menos una opción, confírmela, "
                "indíquele que el equipo hará lo posible por llamarle en alguna de esas fechas, y despídase."
            ),
        },
    },
}


def get_system_prompt(lang, topic, caller_from=None):
    t = TOPICS.get(topic, TOPICS["customer_service"]).get(lang, TOPICS[topic]["en"])

    end_call_rule = (
        "IMPORTANT: Set end_call to true ONLY after the user has explicitly confirmed "
        "the information (said yes, correct, sí, correcto, etc.) AND you have said goodbye. "
        "Never set end_call to true while still asking a question."
    )
    phone_format_rule = (
        "When saying any phone number aloud in the message field, always write it with hyphens "
        "between digit groups (e.g. 408-590-0153), never as a continuous string of digits."
    )

    caller_fmt = format_phone_spoken(caller_from) if caller_from else ""

    if topic == "meeting":
        caller_num_hint = f" Their number appears to be {caller_fmt}." if caller_fmt else ""
        if lang == "en":
            schema = (
                '{\n'
                '  "message": "what to say aloud",\n'
                '  "name": "full name or null",\n'
                '  "phone": "callback phone number or null",\n'
                '  "notes": null,\n'
                '  "end_call": false\n'
                '}'
            )
            return (
                f"You are a friendly pre-screening assistant for Robles AI University, "
                f"which specializes in Business and Artificial Intelligence.\n"
                f"{t['system_extra']}\n"
                f"{caller_num_hint}\n\n"
                f"Ask one question at a time. Be warm and natural. Keep responses SHORT — this is a phone call.\n"
                f"Once you have the caller's name and callback number, confirm them back, "
                f"let them know you will connect them with a team member shortly, and say goodbye.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n"
                f"{phone_format_rule}\n"
                f"{end_call_rule}"
            )
        else:
            schema = (
                '{\n'
                '  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                '  "name": "nombre completo o null",\n'
                '  "phone": "número de rellamada o null",\n'
                '  "notes": null,\n'
                '  "end_call": false\n'
                '}'
            )
            return (
                f"Eres un asistente amigable de pre-selección de Robles AI University. Responde siempre en español.\n"
                f"{t['system_extra']}\n"
                f"{caller_num_hint}\n\n"
                f"Haz una pregunta a la vez. Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n"
                f"Una vez que tengas el nombre y el número de rellamada, confírmalos, "
                f"indícale que le conectarás con un asesor en breve, y despídete.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n"
                f"{phone_format_rule}\n"
                f"{end_call_rule}"
            )

    if topic == "schedule_callback":
        if lang == "en":
            schema = (
                '{\n'
                '  "message": "what to say aloud",\n'
                '  "name": null,\n'
                '  "phone": null,\n'
                '  "notes": "preferred dates and times for callback, comma-separated",\n'
                '  "end_call": false\n'
                '}'
            )
            return (
                f"You are a friendly assistant for Robles AI University, "
                f"which specializes in Business and Artificial Intelligence.\n"
                f"{t['system_extra']}\n\n"
                f"Ask one question at a time. Be warm and natural. Keep responses SHORT — this is a phone call.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n"
                f"{end_call_rule}"
            )
        else:
            schema = (
                '{\n'
                '  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                '  "name": null,\n'
                '  "phone": null,\n'
                '  "notes": "fechas y horas preferidas para la rellamada, separadas por coma",\n'
                '  "end_call": false\n'
                '}'
            )
            return (
                f"Eres un asistente amigable de Robles AI University. Responde siempre en español.\n"
                f"{t['system_extra']}\n\n"
                f"Haz una pregunta a la vez. Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n"
                f"{end_call_rule}"
            )

    # General topics: ai_ml, computer_vision, customer_service
    if lang == "en":
        schema = (
            '{\n'
            '  "message": "what to say aloud",\n'
            '  "name": "full name or null",\n'
            '  "phone": "phone number or null",\n'
            '  "notes": "issue or inquiry details or null",\n'
            '  "end_call": false\n'
            '}'
        )
        phone_instruction = (
            f"Ask: 'Is {caller_fmt} the best number to reach you, or would you prefer a different one?' "
            f"Record whichever number they confirm."
        ) if caller_fmt else "Ask for their callback phone number."
        return (
            f"You are a friendly pre-screening assistant for Robles AI University, which specializes in Business and Artificial Intelligence.\n"
            f"You are collecting information to connect the caller directly with a human specialist on our team.\n"
            f"{t['system_extra']}\n\n"
            f"Follow this sequence strictly, one question at a time:\n"
            f"  Step 1 — Ask for their full name.\n"
            f"  Step 2 — {phone_instruction}\n"
            f"  Step 3 — Ask the 3 topic questions listed above, one at a time, and collect their answers.\n"
            f"  Step 4 — Briefly confirm all collected info, let them know you are connecting them with a specialist, and say goodbye.\n\n"
            f"Be warm and natural. Keep responses SHORT — this is a phone call.\n\n"
            f"Respond ONLY in valid JSON:\n{schema}\n\n"
            f"{phone_format_rule}\n"
            f"{end_call_rule}"
        )
    else:
        schema = (
            '{\n'
            '  "message": "lo que debes decir en voz alta (siempre en español)",\n'
            '  "name": "nombre completo o null",\n'
            '  "phone": "número de teléfono o null",\n'
            '  "notes": "detalles del problema o consulta o null",\n'
            '  "end_call": false\n'
            '}'
        )
        phone_instruction = (
            f"Pregunta: '¿El número {caller_fmt} es el mejor número para contactarle, o prefiere uno diferente?' "
            f"Registra el número que confirme."
        ) if caller_fmt else "Pide su número de teléfono de contacto."
        return (
            f"Eres un asistente amigable de preselección de Robles AI University. Responde siempre en español.\n"
            f"Estás recopilando información para conectar al llamante directamente con un especialista humano de nuestro equipo.\n"
            f"{t['system_extra']}\n\n"
            f"Sigue esta secuencia estrictamente, una pregunta a la vez:\n"
            f"  Paso 1 — Pedir nombre completo.\n"
            f"  Paso 2 — {phone_instruction}\n"
            f"  Paso 3 — Hacer las 3 preguntas del tema listadas arriba, una a la vez, y recopilar las respuestas.\n"
            f"  Paso 4 — Confirmar brevemente la información recopilada, indicar que le conectará con un especialista, y despedirse.\n\n"
            f"Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n"
            f"{phone_format_rule}\n"
            f"{end_call_rule}"
        )


# ── In-memory conversation state ──────────────────────────────────────────────

conversation_store = {}  # {call_sid: [{"role": ..., "content": ...}]}
collected_info     = {}  # {call_sid: {"name": None, "phone": None, "notes": None, "topic": "", "lang": ""}}
outbound_calls     = {}  # {room: outbound_call_sid} — para cancelar si el caller cuelga
failed_rooms       = set()  # rooms donde el agente no contestó → waitUrl redirige a IA
briefed_rooms      = set()  # rooms donde el operador sí contestó (operator-briefing fue llamado)


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Static files ──────────────────────────────────────────────────────────────

@app.route("/intro.wav")
def serve_intro():
    return send_from_directory(".", "intro.wav")


@app.route("/wait-music.wav")
def serve_wait():
    return send_from_directory(".", "wait-music.wav")


# ── Main menu ─────────────────────────────────────────────────────────────────

@app.route("/", methods=['GET', 'POST'])
def main_menu():
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


@app.route("/handle-en", methods=['GET', 'POST'])
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


@app.route("/menu-es", methods=['GET', 'POST'])
def menu_es():
    resp = VoiceResponse()

    gather = Gather(num_digits=1, action="/handle-es", method="POST")
    gather.say(
        "Presione 1 para Agendar una Reunión. "
        "Presione 3 para Servicios de Inteligencia Artificial y Machine Learning. "
        "Presione 4 para Servicios de Visión por Computadora. "
        "Presione 5 para Servicio al Cliente.",
        voice="Google.es-US-Neural2-B"
    )
    resp.append(gather)
    resp.redirect("/menu-es")
    return str(resp)


@app.route("/handle-es", methods=['GET', 'POST'])
def handle_es():
    digit = request.form.get("Digits", "")
    resp  = VoiceResponse()
    topic_map = {"1": "meeting", "3": "ai_ml", "4": "computer_vision", "5": "customer_service"}
    wait_map  = {"1": 1, "3": 3, "4": 4, "5": 5}

    if digit in topic_map:
        resp.redirect(f"/ai-gather?lang=es&topic={topic_map[digit]}")
    else:
        resp.say("Esa no es una opción válida. Por favor intente de nuevo.", voice="Google.es-US-Neural2-B")
        resp.redirect("/menu-es")

    return str(resp)


# ── Forward with conference + AI fallback ────────────────────────────────────

@app.route("/forward", methods=['GET', 'POST'])
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
    twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
    outbound = twilio_client.calls.create(
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


@app.route("/conference-ended", methods=['GET', 'POST'])
def conference_ended():
    """El <Dial> del caller completó (conferencia terminó — agente colgó tras contestar)."""
    lang     = request.args.get("lang", "en")
    topic    = request.args.get("topic", "meeting")
    base_url = request.url_root.rstrip("/")
    print(f"[CONFERENCE-ENDED] lang={lang!r} topic={topic!r}")
    resp = VoiceResponse()
    resp.redirect(f"{base_url}/ai-gather?lang={lang}&topic={topic}")
    return str(resp)


@app.route("/conference-status", methods=['GET', 'POST'])
def conference_status():
    """Caller colgó — cancela la llamada saliente al agente."""
    room         = request.values.get("room", "")
    outbound_sid = outbound_calls.pop(room, None)
    failed_rooms.discard(room)
    if outbound_sid:
        try:
            Client(ACCOUNT_SID, AUTH_TOKEN).calls(outbound_sid).update(status="canceled")
        except Exception:
            pass
    return ("", 204)


@app.route("/agent-status", methods=['GET', 'POST'])
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
                Client(ACCOUNT_SID, AUTH_TOKEN).calls(caller_sid).update(
                    url=f"{base_url}/ai-gather?lang={lang}&topic={topic}",
                    method="POST",
                )
                print(f"[AGENT-STATUS] REST redirect OK → caller_sid={caller_sid!r}")
            except Exception as e:
                print(f"[AGENT-STATUS] REST redirect failed: {e}")

    return ("", 204)


@app.route("/hold-music/<int:num>", methods=['GET', 'POST'])
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


# ── AI conversation ───────────────────────────────────────────────────────────

@app.route("/ai-gather", methods=['GET', 'POST'])
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


@app.route("/ai-respond", methods=['GET', 'POST'])
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
            Client(ACCOUNT_SID, AUTH_TOKEN).messages.create(
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


# ── Connect to human operator after AI collects data ─────────────────────────

@app.route("/connect-operator", methods=['GET', 'POST'])
def connect_operator():
    lang       = request.values.get("lang", "en")
    caller_sid = request.values.get("caller_sid", request.form.get("CallSid", ""))
    voice      = get_voice(lang)
    room       = f"room-{uuid.uuid4().hex}"
    base_url   = request.url_root.rstrip("/")

    hold_msg = (
        "Please hold while I connect you with one of our team members."
        if lang == "en" else
        "Por favor espere mientras le conecto con uno de nuestros asesores."
    )

    resp = VoiceResponse()
    resp.say(hold_msg, voice=voice)

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
        recording_status_callback=f"{base_url}/recording-ready?caller_sid={caller_sid}&lang={lang}",
        recording_status_callback_method="POST",
    )
    resp.append(dial)

    # Llamar al operador; cuando conteste, escucha el briefing y luego se une a la conferencia
    twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
    outbound = twilio_client.calls.create(
        to=FORWARD_TO,
        from_=TWILIO_FROM,
        url=f"{base_url}/operator-briefing?caller_sid={caller_sid}&room={room}&lang={lang}",
        status_callback=f"{base_url}/operator-status?room={room}&caller_sid={caller_sid}&lang={lang}",
        status_callback_method="POST",
        status_callback_event=["completed"],
    )
    outbound_calls[room] = outbound.sid
    return str(resp)


@app.route("/operator-hold-music", methods=['GET', 'POST'])
def operator_hold_music():
    room  = request.values.get("room", "")
    lang  = request.values.get("lang", "en")
    base_url = request.url_root.rstrip("/")

    if room and room in failed_rooms:
        failed_rooms.discard(room)
        resp = VoiceResponse()
        resp.redirect(f"{base_url}/no-availability?lang={lang}")
        return str(resp)

    resp = VoiceResponse()
    resp.play(request.url_root + "wait-music.wav", loop=1)
    return str(resp)


@app.route("/operator-briefing", methods=['GET', 'POST'])
def operator_briefing():
    """TwiML para el operador: escucha datos del caller, luego se une a la conferencia."""
    caller_sid = request.values.get("caller_sid", "")
    room       = request.values.get("room", "")
    lang       = request.values.get("lang", "en")
    voice      = get_voice(lang)

    # El operador contestó → marcar room para que operator-status no lo trate como no-answer
    if room:
        briefed_rooms.add(room)

    info   = collected_info.get(caller_sid, {})
    name   = info.get("name") or "Unknown"
    phone  = info.get("phone") or "Unknown"
    notes  = info.get("notes") or ""
    topic  = info.get("topic", "")
    topic_label = TOPICS.get(topic, {}).get(lang, {}).get("label", topic)

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


@app.route("/operator-status", methods=['GET', 'POST'])
def operator_status():
    """Callback cuando la llamada al operador termina."""
    call_status = request.values.get("CallStatus", "")
    room        = request.values.get("room", "")
    caller_sid  = request.values.get("caller_sid", "")
    lang        = request.values.get("lang", "en")
    base_url    = request.url_root.rstrip("/")

    print(f"[OPERATOR-STATUS] CallStatus={call_status!r} room={room!r}")

    outbound_calls.pop(room, None)

    # "completed" = operador rechazó/canceló antes de unirse a la conferencia
    # Si briefed_rooms contiene el room, el operador SÍ contestó → no redirigir
    operator_answered = room in briefed_rooms
    briefed_rooms.discard(room)

    no_answer_statuses = {"no-answer", "busy", "failed", "canceled"}
    is_no_answer = call_status in no_answer_statuses or (call_status == "completed" and not operator_answered)

    print(f"[OPERATOR-STATUS] CallStatus={call_status!r} operator_answered={operator_answered} is_no_answer={is_no_answer}")

    if is_no_answer:
        if room:
            failed_rooms.add(room)
        if caller_sid:
            try:
                Client(ACCOUNT_SID, AUTH_TOKEN).calls(caller_sid).update(
                    url=f"{base_url}/no-availability?lang={lang}",
                    method="POST",
                )
                print(f"[OPERATOR-STATUS] Redirected caller to no-availability")
            except Exception as e:
                print(f"[OPERATOR-STATUS] REST redirect failed: {e}")

    return ("", 204)


@app.route("/no-availability", methods=['GET', 'POST'])
def no_availability():
    """Operador no disponible — iniciar flujo de IA para agendar rellamada."""
    lang     = request.values.get("lang", "en")
    base_url = request.url_root.rstrip("/")
    resp = VoiceResponse()
    resp.redirect(f"{base_url}/ai-gather?lang={lang}&topic=schedule_callback")
    return str(resp)


@app.route("/recording-ready", methods=['GET', 'POST'])
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

        # Transcribir con Whisper
        import io
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=("recording.mp3", io.BytesIO(audio_bytes), "audio/mpeg"),
        )
        text = transcript.text

        # Resumir con GPT
        info = collected_info.get(caller_sid, {})
        summary_prompt = (
            f"The following is a transcript of a business call between a customer and an operator at Robles AI.\n"
            f"Customer info: Name={info.get('name')}, Phone={info.get('phone')}, Notes={info.get('notes')}.\n\n"
            f"Transcript:\n{text}\n\n"
            f"Please provide a concise summary of the conversation including: main topics discussed, "
            f"agreements or next steps, and any important details."
        ) if lang == "en" else (
            f"La siguiente es la transcripción de una llamada de negocios entre un cliente y un asesor de Robles AI.\n"
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
        topic_label = TOPICS.get(info.get("topic",""), {}).get(lang, {}).get("label", info.get("topic",""))

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

    except Exception as e:
        print(f"[RECORDING ERROR] {e}")

    return ("", 204)


@app.route("/meeting-ended", methods=['GET', 'POST'])
def meeting_ended():
    """Dial action cuando la conferencia termina (operador colgó tras la llamada)."""
    lang  = request.values.get("lang", "en")
    voice = get_voice(lang)

    msg = "Thank you for calling Robles AI. Have a great day!" if lang == "en" else "Gracias por llamar a Robles AI. ¡Que tenga un excelente día!"

    resp = VoiceResponse()
    resp.say(msg, voice=voice)
    resp.hangup()
    return str(resp)


if __name__ == "__main__":
    app.run(debug=True)
