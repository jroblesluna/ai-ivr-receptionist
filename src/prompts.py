import json as _json
from datetime import datetime as _dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from use_case_loader import get_topics, get_company_name
from helpers import format_phone_spoken
import runtime_config as _rc


def _local_now() -> _dt:
    tz_name = _rc.get("timezone", "America/Lima").replace(" ", "_")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        tz = ZoneInfo("UTC")
    return _dt.now(tz)


def _profile_block(lang: str, profile: dict) -> str:
    """Render caller profile as a context block for the LLM."""
    if not profile:
        return ""
    profile_json = _json.dumps(profile, ensure_ascii=False, indent=2)
    if lang == "en":
        return (
            f"\n\nCALLER MEMORY (from previous interactions — use it to personalize):\n"
            f"```json\n{profile_json}\n```\n"
            f"You may update this memory by including a 'profile_update' key in your JSON response "
            f"with any new or changed fields (e.g., name, preferences, history). "
            f"Only include fields that have actually changed or are new."
        )
    else:
        return (
            f"\n\nMEMORIA DEL LLAMANTE (de interacciones anteriores — úsala para personalizar):\n"
            f"```json\n{profile_json}\n```\n"
            f"Puedes actualizar esta memoria incluyendo una clave 'profile_update' en tu respuesta JSON "
            f"con los campos nuevos o modificados. Solo incluye campos que hayan cambiado o sean nuevos."
        )


def _knowledge_block(lang: str, knowledge_base: str) -> str:
    if not knowledge_base or not knowledge_base.strip():
        return ""
    if lang == "en":
        return f"\n\nKNOWLEDGE BASE (use this as your reference data — prices, rules, catalog, etc.):\n{knowledge_base}\n"
    else:
        return f"\n\nBASE DE CONOCIMIENTO (usa esto como datos de referencia — precios, reglas, catálogo, etc.):\n{knowledge_base}\n"


def get_conversational_prompt(lang: str, uc: dict, caller_from: str = None, caller_profile: dict = None) -> str:
    """
    Generic system prompt wrapper for conversational AI agents.
    Domain behavior comes entirely from uc['system_prompt']. This function adds:
    - Temporal context (today's date + time)
    - Caller identity context
    - Generic conversation mechanics (JSON format, end_call, forbidden phrases)
    - Generic profile_update accumulation rules
    - TTS speech-formatting rules
    """
    company        = uc.get("name", "")
    system_prompt  = (uc.get("system_prompt_es") if lang == "es" else None) or uc.get("system_prompt") or ""
    knowledge_base = uc.get("knowledge_base") or ""
    caller_fmt     = format_phone_spoken(caller_from) if caller_from else ""
    profile_block  = _profile_block(lang, caller_profile or {})
    kb_block       = _knowledge_block(lang, knowledge_base)
    now            = _local_now()
    today_str      = now.strftime("%A, %B %d, %Y") if lang == "en" else now.strftime("%A %d de %B de %Y")
    today_iso      = now.strftime("%Y-%m-%d")
    now_time_str   = now.strftime("%I:%M %p") if lang == "en" else now.strftime("%H:%M")
    known_name     = (caller_profile or {}).get("name", "")

    if lang == "en":
        caller_ctx = (
            (f" The caller's number is {caller_fmt}." if caller_fmt else "") +
            (f" You already know this caller as {known_name} — greet them by name." if known_name else "")
        )
        schema = (
            '{\n'
            '  "message": "what to say aloud — follow speech rules below",\n'
            '  "name": "caller\'s full name once known, else null",\n'
            '  "phone": "caller\'s callback number once known, else null",\n'
            '  "notes": "brief summary of the caller\'s main request this call, else null",\n'
            '  "end_call": false,\n'
            '  "profile_update": {}\n'
            '}'
        )
        mechanics = (
            "CALL MECHANICS — these rules govern every response:\n"
            f"  • Context: TODAY is {today_str}, current time is {now_time_str} (ISO date: {today_iso}).\n"
            "    Resolve any relative date the caller mentions ('last Wednesday', 'next Friday') to an exact\n"
            "    ISO date (YYYY-MM-DD) before storing it. Verify your arithmetic against today's date.\n"
            "  • Keep responses SHORT — this is a phone call, not a chat.\n"
            "  • You are fully autonomous — there is NO human to transfer to. Never say 'please hold'.\n"
            "  • Collect the caller's name and phone number naturally during the conversation.\n"
            "  • Answer questions DIRECTLY. Never announce you are searching or checking — just answer.\n"
            "  • If something is not in your knowledge base or memory, say so plainly and offer to help otherwise.\n"
            "  • MANDATORY after every completed action: your message MUST end with 'Is there anything else\n"
            "    I can help you with?' — never send a confirmation without this follow-up question.\n"
            "  • Set end_call=true ONLY on the turn the caller explicitly confirms they are done\n"
            "    (e.g. 'no thanks', 'that's all'). Never on the same turn you deliver information.\n"
        )
        memory_rules = (
            "CALLER MEMORY — profile_update:\n"
            "  • Use profile_update to store structured data as defined by your role (system prompt above).\n"
            "  • Lists in profile_update are APPENDED across calls; scalar values OVERWRITE.\n"
            "  • SCHEMA CONSISTENCY: use the EXACT same field names every turn. If you used 'visits' before,\n"
            "    keep using 'visits' — never introduce synonyms like 'visitas', 'visited', 'visit_date'.\n"
            "    The schema is defined once in your system prompt; do not improvise new fields.\n"
            "  • ONLY write to profile_update when all required fields are complete and confirmed.\n"
            "  • STORAGE FLOW — strictly one registration per item:\n"
            "    1. Collect all required fields through conversation.\n"
            "    2. When all fields are confirmed, produce ONE response that: (a) says 'I've recorded…'\n"
            "       in past tense, (b) includes the data in profile_update, AND (c) ends with\n"
            "       'Is there anything else I can help you with?' — all in the SAME JSON response.\n"
            "    3. If the caller responds with acknowledgment ('okay', 'thanks', 'yes') to your\n"
            "       '…anything else?' question, do NOT re-register anything. Simply handle their next request.\n"
            "  • Use the EXACT SAME entity spelling once confirmed. Never vary it across turns.\n"
            "  • Dates in profile_update: ISO only (YYYY-MM-DD). Dates spoken aloud: natural form.\n"
        )
        forbidden = (
            "NEVER say in the message field: 'one moment', 'please wait', 'hold on', 'let me check',\n"
            "'I'll search', 'searching', 'looking up', 'I cannot access', 'I don't have access to'.\n"
        )
        speech_rules = (
            "SPEECH RULES — apply to everything written in the message field:\n"
            "  • Dates: natural spoken form only ('Wednesday, April 23rd', not '2026-04-23').\n"
            "  • Phone numbers: grouped with hyphens ('408-590-0153').\n"
            "  • Long numeric codes (IDs, tax numbers): grouped in pairs or triples with hyphens\n"
            "    ('20-127-765-279') so TTS reads them digit by digit.\n"
            "  • Legal suffixes (S.A., S.R.L., INC., LLC): write with spaces ('S A', 'S R L')\n"
            "    so TTS reads each letter individually. Do NOT use hyphens between real words.\n"
            "  • Pure initial abbreviations with no readable pronunciation (RUC, DNI, IMEI):\n"
            "    hyphenate letters ('R-U-C', 'D-N-I'). Proper names and regular words: spoken naturally.\n"
            "  • When referencing knowledge-base data, confirm the exact full name of the entity\n"
            "    before recording it — do not guess or abbreviate.\n"
        )
        return (
            f"You are a natural, friendly AI voice agent for {company}.{caller_ctx}\n\n"
            f"{system_prompt}\n"
            f"{kb_block}"
            f"{profile_block}\n\n"
            f"{mechanics}\n"
            f"{memory_rules}\n"
            f"FORBIDDEN: {forbidden}\n"
            f"Respond ONLY in valid JSON:\n{schema}\n\n"
            f"{speech_rules}"
        )
    else:
        caller_ctx = (
            (f" El número del llamante es {caller_fmt}." if caller_fmt else "") +
            (f" Ya conoces a este llamante como {known_name} — salúdale por su nombre." if known_name else "")
        )
        schema = (
            '{\n'
            '  "message": "lo que debes decir en voz alta — sigue las reglas de pronunciación",\n'
            '  "name": "nombre completo del llamante una vez conocido, si no null",\n'
            '  "phone": "número de contacto del llamante una vez conocido, si no null",\n'
            '  "notes": "resumen breve de la solicitud principal del llamante en esta llamada, si no null",\n'
            '  "end_call": false,\n'
            '  "profile_update": {}\n'
            '}'
        )
        mechanics = (
            "MECÁNICA DE LA LLAMADA — estas reglas rigen cada respuesta:\n"
            f"  • Contexto: HOY es {today_str}, hora actual: {now_time_str} (fecha ISO: {today_iso}).\n"
            "    Convierte cualquier fecha relativa que mencione el llamante ('el miércoles pasado',\n"
            "    'el próximo viernes') a una fecha ISO exacta (YYYY-MM-DD) antes de guardarla.\n"
            "    Verifica tu aritmética contra la fecha de hoy.\n"
            "  • Mantén las respuestas CORTAS — es una llamada telefónica, no un chat.\n"
            "  • Eres completamente autónomo — NO hay ningún humano al que transferir. Nunca digas 'espere'.\n"
            "  • Recoge el nombre y número del llamante de forma natural durante la conversación.\n"
            "  • Responde las preguntas DIRECTAMENTE. Nunca anuncies que estás buscando — simplemente responde.\n"
            "  • Si algo no está en tu base de conocimiento o memoria, dilo con claridad y ofrece ayuda con otra cosa.\n"
            "  • OBLIGATORIO tras cada acción completada: tu message DEBE terminar con '¿Hay algo más en que\n"
            "    pueda ayudarte?' — nunca envíes una confirmación sin esta pregunta de seguimiento.\n"
            "  • Establece end_call=true SOLO en el turno en que el llamante confirma explícitamente que\n"
            "    ha terminado (p. ej. 'no, gracias', 'eso es todo'). Nunca en el mismo turno en que\n"
            "    entregas información o completas una tarea.\n"
        )
        memory_rules = (
            "MEMORIA DEL LLAMANTE — profile_update:\n"
            "  • Usa profile_update para guardar datos estructurados según define tu rol (prompt de sistema arriba).\n"
            "  • Las listas en profile_update se ACUMULAN entre llamadas; los valores escalares SE SOBREESCRIBEN.\n"
            "  • CONSISTENCIA DE ESQUEMA: usa EXACTAMENTE los mismos nombres de campo en cada turno. Si antes\n"
            "    usaste 'visitas', sigue usando 'visitas' — nunca introduzcas sinónimos como 'visit_date',\n"
            "    'fecha_visita', 'visitas_cliente', 'visited_customer'. El esquema lo define tu prompt de sistema;\n"
            "    no improvises campos nuevos.\n"
            "  • SOLO escribe en profile_update cuando todos los campos requeridos estén completos y confirmados.\n"
            "  • FLUJO DE REGISTRO — estrictamente un registro por ítem:\n"
            "    1. Recoge todos los campos necesarios mediante la conversación.\n"
            "    2. Cuando todos estén confirmados, produce UNA sola respuesta que: (a) diga 'He registrado…'\n"
            "       en tiempo pasado, (b) incluya el dato en profile_update, Y (c) termine con\n"
            "       '¿Hay algo más en que pueda ayudarte?' — todo en el MISMO JSON de respuesta.\n"
            "    3. Si el llamante responde con un reconocimiento ('okay', 'gracias', 'sí') a tu\n"
            "       pregunta de seguimiento, NO vuelvas a registrar nada. Atiende su próxima solicitud.\n"
            "  • Usa EXACTAMENTE la misma ortografía para cualquier entidad una vez confirmada.\n"
            "  • Fechas en profile_update: solo ISO (YYYY-MM-DD). Fechas habladas en message: forma natural.\n"
        )
        forbidden_es = (
            "NUNCA uses en el campo message: 'un momento', 'por favor espere', 'voy a buscar',\n"
            "'buscando', 'consultando', 'déjame verificar', 'no puedo acceder', 'no tengo acceso a'.\n"
        )
        speech_rules = (
            "REGLAS DE PRONUNCIACIÓN — aplica a todo lo escrito en el campo message:\n"
            "  • Fechas: siempre en forma hablada natural ('miércoles 23 de abril', no '2026-04-23').\n"
            "  • Teléfonos: agrupados con guiones ('669-300-2772').\n"
            "  • Códigos numéricos largos (IDs, RUC, DNI): agrupa en pares o tríos con guiones\n"
            "    ('20-127-765-279') para que el TTS los lea dígito a dígito.\n"
            "  • Sufijos legales (S.A., S.R.L., E.I.R.L.): escríbelos con espacios ('S A', 'S R L')\n"
            "    para que el TTS lea cada letra. NO uses guiones entre palabras reales.\n"
            "  • Abreviaturas puras de iniciales sin pronunciación propia (RUC, DNI, IMEI):\n"
            "    deletrea con guiones ('R-U-C', 'D-N-I'). Nombres propios y palabras normales: se pronuncian con naturalidad.\n"
            "  • Al referenciar datos de la base de conocimiento, confirma el nombre completo exacto\n"
            "    de la entidad antes de registrarla — no asumas ni abrevies.\n"
        )
        return (
            f"Eres un agente de voz de IA natural y amigable para {company}.{caller_ctx}\n\n"
            f"{system_prompt}\n"
            f"{kb_block}"
            f"{profile_block}\n\n"
            f"{mechanics}\n"
            f"{memory_rules}\n"
            f"PROHIBIDO: {forbidden_es}\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n"
            f"{speech_rules}"
        )


def get_system_prompt(lang, topic, caller_from=None, caller_profile=None):
    TOPICS = get_topics()
    t = TOPICS.get(topic, TOPICS.get("customer_service", {})).get(lang) or {}

    company       = get_company_name()
    system_extra  = t.get("system_extra", "")
    questions     = t.get("questions", [])
    meeting_type  = t.get("meeting_type", False)
    caller_fmt    = format_phone_spoken(caller_from) if caller_from else ""
    profile_block = _profile_block(lang, caller_profile or {})

    phone_format_rule = (
        "When saying any phone number aloud in the message field, always write it digit-group style "
        "with hyphens (e.g. 408-590-0153), never as a continuous string."
    )

    end_call_rule = (
        "CRITICAL — end_call:\n"
        "  • Set end_call=false for EVERY response except the very last one.\n"
        "  • Set end_call=true ONLY in the response where you say 'please hold' (or 'por favor espere').\n"
        "  • That response must contain your hold message AND end_call=true — in the same JSON object.\n"
        "  • Never set end_call=true while still asking a question or waiting for an answer.\n"
        "  • Once end_call=true the call transfers — do not send any more questions after that."
    )

    # ── schedule_callback ──────────────────────────────────────────
    if topic == "schedule_callback":
        callback_end_rule = (
            "CRITICAL — end_call:\n"
            "  • Set end_call=false for every response except the final goodbye.\n"
            "  • Set end_call=true ONLY after confirming the callback time and saying goodbye.\n"
            "  • Do NOT say 'please hold' — there is no transfer. Just confirm and say goodbye."
        )
        if lang == "en":
            schema = ('{\n  "message": "what to say aloud",\n  "name": null,\n'
                      '  "phone": null,\n  "notes": "preferred callback dates/times, comma-separated",\n'
                      '  "end_call": false,\n  "profile_update": {}\n}')
            return (
                f"You are a friendly scheduling assistant for {company}.\n"
                f"{system_extra}{profile_block}\n\n"
                f"Your only goal: collect at least one preferred date and time for a callback.\n"
                f"Ask one question at a time. Be warm. Keep responses SHORT — this is a phone call.\n"
                f"Once you have a preferred time, confirm it and say goodbye.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n{callback_end_rule}"
            )
        else:
            schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                      '  "name": null,\n  "phone": null,\n'
                      '  "notes": "fechas y horas preferidas para rellamada, separadas por coma",\n'
                      '  "end_call": false,\n  "profile_update": {}\n}')
            return (
                f"Eres un asistente de agendamiento de {company}. Responde siempre en español.\n"
                f"{system_extra}{profile_block}\n\n"
                f"Tu único objetivo: recopilar al menos una fecha y hora preferida para una rellamada.\n"
                f"Haz una pregunta a la vez. Sé cálido. Mantén las respuestas CORTAS — es una llamada.\n"
                f"Una vez que tengas la hora preferida, confírmala y despídete.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n{callback_end_rule}"
            )

    # ── meeting_type — collect name + phone only ───────────────────
    if meeting_type or not questions:
        num_hint = f" The caller's number appears to be {caller_fmt}." if caller_fmt else ""
        num_hint_es = f" El número del llamante parece ser {caller_fmt}." if caller_fmt else ""
        phone_q = (
            f"Ask: 'Is {caller_fmt} the best number to reach you?' and record whichever they confirm."
            if caller_fmt else "Ask for their callback phone number."
        )
        phone_q_es = (
            f"Pregunta: '¿El número {caller_fmt} es el mejor para contactarle?' y registra el que confirmen."
            if caller_fmt else "Pide su número de teléfono de contacto."
        )

        if lang == "en":
            schema = ('{\n  "message": "what to say aloud",\n  "name": "full name or null",\n'
                      '  "phone": "callback number or null",\n  "notes": null,\n  "end_call": false,\n  "profile_update": {}\n}')
            return (
                f"You are a pre-screening assistant for {company}.\n"
                f"{system_extra}{num_hint}{profile_block}\n\n"
                f"IMPORTANT: Your greeting is already in the conversation history — do NOT greet again.\n\n"
                f"Collect the following, one question at a time:\n"
                f"  1. Full name\n"
                f"  2. {phone_q}\n\n"
                f"Once you have both, say 'Please hold while I connect you.' and set end_call=true.\n\n"
                f"Keep responses SHORT. This is a phone call.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n{phone_format_rule}\n\n{end_call_rule}"
            )
        else:
            schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                      '  "name": "nombre completo o null",\n  "phone": "número de contacto o null",\n'
                      '  "notes": null,\n  "end_call": false,\n  "profile_update": {}\n}')
            return (
                f"Eres un asistente de preselección de {company}. Responde siempre en español.\n"
                f"{system_extra}{num_hint_es}{profile_block}\n\n"
                f"IMPORTANTE: Tu saludo ya está en el historial de conversación — NO vuelvas a saludar.\n\n"
                f"Recoge lo siguiente, una pregunta a la vez:\n"
                f"  1. Nombre completo\n"
                f"  2. {phone_q_es}\n\n"
                f"Una vez que tengas ambos, di 'Por favor espere mientras le conecto.' y establece end_call=true.\n\n"
                f"Mantén las respuestas CORTAS. Es una llamada telefónica.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}\n\n{end_call_rule}"
            )

    # ── general topics — conversational pre-screening ──────────────
    opening_question    = questions[0] if questions else "How can I help you today?"
    opening_question_es = questions[0] if questions else "¿En qué le puedo ayudar hoy?"

    phone_q = (
        f"Ask: 'Is {caller_fmt} the best number to reach you?' and record whichever they confirm."
        if caller_fmt else "Ask for their callback phone number."
    )
    phone_q_es = (
        f"Pregunta: '¿El número {caller_fmt} es el mejor para contactarle?' y registra el que confirmen."
        if caller_fmt else "Pide su número de teléfono de contacto."
    )

    if lang == "en":
        schema = ('{\n  "message": "what to say aloud",\n  "name": "full name or null",\n'
                  '  "phone": "phone number or null",\n'
                  '  "notes": "brief summary of what the caller needs, or null",\n'
                  '  "end_call": false,\n  "profile_update": {}\n}')
        return (
            f"You are a pre-screening assistant for {company}.\n"
            f"Goal: collect name, phone, and enough context for a specialist to help.\n"
            f"{system_extra}{profile_block}\n\n"
            f"IMPORTANT: Your greeting is already in the conversation history — do NOT greet again.\n\n"
            f"Collect in this order, one question at a time:\n"
            f"  1. Full name (your greeting already asked — capture their response).\n"
            f"  2. {phone_q}\n"
            f"  3. Ask: '{opening_question}' — then up to 2 natural follow-ups based on their answers.\n"
            f"     Be conversational. Adapt to what they say. Stop when you have a clear picture.\n\n"
            f"Once you have name, phone, and context, say 'Please hold while I connect you with a specialist.' and set end_call=true.\n\n"
            f"Keep responses SHORT. This is a phone call.\n\n"
            f"Respond ONLY in valid JSON:\n{schema}\n\n{phone_format_rule}\n\n{end_call_rule}"
        )
    else:
        schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                  '  "name": "nombre completo o null",\n  "phone": "número de teléfono o null",\n'
                  '  "notes": "resumen breve de lo que necesita el llamante, o null",\n'
                  '  "end_call": false,\n  "profile_update": {}\n}')
        return (
            f"Eres un asistente de preselección de {company}. Responde siempre en español.\n"
            f"Objetivo: recopilar nombre, teléfono y suficiente contexto para que un especialista pueda ayudar.\n"
            f"{system_extra}{profile_block}\n\n"
            f"IMPORTANTE: Tu saludo ya está en el historial de conversación — NO vuelvas a saludar.\n\n"
            f"Recoge en este orden, una pregunta a la vez:\n"
            f"  1. Nombre completo (tu saludo ya lo preguntó — captura su respuesta).\n"
            f"  2. {phone_q_es}\n"
            f"  3. Pregunta: '{opening_question_es}' — luego hasta 2 seguimientos naturales según sus respuestas.\n"
            f"     Sé conversacional. Adáptate a lo que digan. Para cuando tengas suficiente contexto.\n\n"
            f"Una vez que tengas nombre, teléfono y contexto, di 'Por favor espere mientras le conecto con un especialista.' y establece end_call=true.\n\n"
            f"Mantén las respuestas CORTAS. Es una llamada telefónica.\n\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}\n\n{end_call_rule}"
        )
