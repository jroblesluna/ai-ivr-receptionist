from use_case_loader import get_topics, get_company_name
from helpers import format_phone_spoken


def get_system_prompt(lang, topic, caller_from=None):
    TOPICS = get_topics()
    t = TOPICS.get(topic, TOPICS.get("customer_service", {})).get(lang) or {}

    company      = get_company_name()
    system_extra = t.get("system_extra", "")
    questions    = t.get("questions", [])
    meeting_type = t.get("meeting_type", False)
    caller_fmt   = format_phone_spoken(caller_from) if caller_from else ""

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
                      '  "end_call": false\n}')
            return (
                f"You are a friendly scheduling assistant for {company}.\n"
                f"{system_extra}\n\n"
                f"Your only goal: collect at least one preferred date and time for a callback.\n"
                f"Ask one question at a time. Be warm. Keep responses SHORT — this is a phone call.\n"
                f"Once you have a preferred time, confirm it and say goodbye.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n{callback_end_rule}"
            )
        else:
            schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                      '  "name": null,\n  "phone": null,\n'
                      '  "notes": "fechas y horas preferidas para rellamada, separadas por coma",\n'
                      '  "end_call": false\n}')
            return (
                f"Eres un asistente de agendamiento de {company}. Responde siempre en español.\n"
                f"{system_extra}\n\n"
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
                      '  "phone": "callback number or null",\n  "notes": null,\n  "end_call": false\n}')
            return (
                f"You are a pre-screening assistant for {company}.\n"
                f"{system_extra}{num_hint}\n\n"
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
                      '  "notes": null,\n  "end_call": false\n}')
            return (
                f"Eres un asistente de preselección de {company}. Responde siempre en español.\n"
                f"{system_extra}{num_hint_es}\n\n"
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
                  '  "notes": "brief summary of what the caller needs, or null",\n  "end_call": false\n}')
        return (
            f"You are a pre-screening assistant for {company}.\n"
            f"Goal: collect name, phone, and enough context for a specialist to help.\n"
            f"{system_extra}\n\n"
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
                  '  "notes": "resumen breve de lo que necesita el llamante, o null",\n  "end_call": false\n}')
        return (
            f"Eres un asistente de preselección de {company}. Responde siempre en español.\n"
            f"Objetivo: recopilar nombre, teléfono y suficiente contexto para que un especialista pueda ayudar.\n"
            f"{system_extra}\n\n"
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
