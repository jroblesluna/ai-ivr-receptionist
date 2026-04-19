import json as _json
from use_case_loader import get_topics, get_company_name
from helpers import format_phone_spoken


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


def get_conversational_prompt(lang: str, uc: dict, caller_from: str = None, caller_profile: dict = None) -> str:
    """System prompt for conversational-type demos (no digit menu, natural AI conversation)."""
    company       = uc.get("name", "")
    system_prompt = uc.get("system_prompt") or ""
    caller_fmt    = format_phone_spoken(caller_from) if caller_from else ""
    profile_block = _profile_block(lang, caller_profile or {})

    phone_format_rule = (
        "When saying any phone number aloud in the message field, always write it digit-group style "
        "with hyphens (e.g. 408-590-0153), never as a continuous string."
    )

    if lang == "en":
        caller_hint = f" The caller's number appears to be {caller_fmt}." if caller_fmt else ""
        known_name  = (caller_profile or {}).get("name", "")
        greeting_hint = (
            f" You already know this caller as {known_name} — greet them by name."
            if known_name else ""
        )
        schema = (
            '{\n  "message": "what to say aloud",\n'
            '  "name": "full name or null",\n'
            '  "phone": "callback number or null",\n'
            '  "notes": "summary of the conversation purpose or null",\n'
            '  "end_call": false,\n'
            '  "profile_update": {}\n}'
        )
        return (
            f"You are a natural, friendly AI receptionist for {company}.{caller_hint}{greeting_hint}\n\n"
            f"{system_prompt}\n"
            f"{profile_block}\n\n"
            f"IMPORTANT RULES:\n"
            f"  • Respond naturally as if you are a human receptionist — no robotic prompts.\n"
            f"  • Keep responses SHORT — this is a phone call, not a chat.\n"
            f"  • Collect the caller's name and phone number naturally during the conversation.\n"
            f"  • When you have name + phone and the conversation goal is reached: say 'Please hold' and set end_call=true.\n"
            f"  • Use profile_update to save any new information you learn about the caller.\n\n"
            f"Respond ONLY in valid JSON:\n{schema}\n\n{phone_format_rule}"
        )
    else:
        caller_hint = f" El número del llamante parece ser {caller_fmt}." if caller_fmt else ""
        known_name  = (caller_profile or {}).get("name", "")
        greeting_hint = (
            f" Ya conoces a este llamante como {known_name} — salúdale por su nombre."
            if known_name else ""
        )
        schema = (
            '{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
            '  "name": "nombre completo o null",\n'
            '  "phone": "número de contacto o null",\n'
            '  "notes": "resumen del propósito de la conversación o null",\n'
            '  "end_call": false,\n'
            '  "profile_update": {}\n}'
        )
        return (
            f"Eres una recepcionista de IA natural y amigable para {company}.{caller_hint}{greeting_hint}\n\n"
            f"{system_prompt}\n"
            f"{profile_block}\n\n"
            f"REGLAS IMPORTANTES:\n"
            f"  • Responde de forma natural como si fueras una recepcionista humana.\n"
            f"  • Mantén las respuestas CORTAS — es una llamada telefónica.\n"
            f"  • Recoge el nombre y número del llamante de forma natural durante la conversación.\n"
            f"  • Cuando tengas nombre + teléfono y el objetivo se haya logrado: di 'Por favor espere' y establece end_call=true.\n"
            f"  • Usa profile_update para guardar cualquier nueva información del llamante.\n\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}"
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
                f"Once you have both:\n"
                f"  - Read back: 'I have your name as [name] and number as [phone]. Is that correct?'\n"
                f"  - If YES → say 'Please hold while I connect you.' and set end_call=true.\n"
                f"  - If NO  → ask which detail needs correcting, fix it, then confirm again.\n\n"
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
                f"Una vez que tengas ambos:\n"
                f"  - Repite: 'Tengo su nombre como [nombre] y su número como [teléfono]. ¿Es correcto?'\n"
                f"  - Si SÍ → di 'Por favor espere mientras le conecto.' y establece end_call=true.\n"
                f"  - Si NO → pregunta qué dato está mal, corrígelo y vuelve a confirmar.\n\n"
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
            f"Once you have name, phone, and context:\n"
            f"  - Summarize: 'So your name is [name], number [phone], and you need [brief context]. Is that correct?'\n"
            f"  - If YES → say 'Please hold while I connect you with a specialist.' and set end_call=true.\n"
            f"  - If NO  → ask what needs correcting, fix it, then confirm again.\n\n"
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
            f"Una vez que tengas nombre, teléfono y contexto:\n"
            f"  - Resume: 'Su nombre es [nombre], número [teléfono], y necesita [contexto breve]. ¿Es correcto?'\n"
            f"  - Si SÍ → di 'Por favor espere mientras le conecto con un especialista.' y establece end_call=true.\n"
            f"  - Si NO → pregunta qué está mal, corrígelo y vuelve a confirmar.\n\n"
            f"Mantén las respuestas CORTAS. Es una llamada telefónica.\n\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}\n\n{end_call_rule}"
        )
