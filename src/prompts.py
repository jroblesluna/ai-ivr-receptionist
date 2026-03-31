from use_case_loader import get_topics, get_company_name
from helpers import format_phone_spoken


def get_system_prompt(lang, topic, caller_from=None):
    print("Starting get_system_prompt")
    print("lang: ",lang)
    print("topic: ",topic)
    print("caller_from: ",caller_from)

    TOPICS = get_topics()
    t = TOPICS.get(topic, TOPICS.get("customer_service", {})).get(lang) or {}

    company        = get_company_name()
    system_extra   = t.get("system_extra", "")
    questions      = t.get("questions", [])
    meeting_type   = t.get("meeting_type", False)
    caller_fmt     = format_phone_spoken(caller_from) if caller_from else ""

    end_call_rule = (
        "IMPORTANT: Set end_call to true ONLY after the user has explicitly confirmed their information "
        "(said yes, correct, sí, correcto, etc.) AND you have told them to please hold. "
        "Never set end_call to true while still asking a question or waiting for confirmation."
    )
    phone_format_rule = (
        "When saying any phone number aloud in the message field, always write it with hyphens "
        "between digit groups (e.g. 408-590-0153), never as a continuous string of digits."
    )

    # ── schedule_callback ──────────────────────────────────────
    if topic == "schedule_callback":
        if lang == "en":
            schema = ('{\n  "message": "what to say aloud",\n  "name": null,\n'
                      '  "phone": null,\n  "notes": "preferred dates and times, comma-separated",\n'
                      '  "end_call": false\n}')
            return (
                f"You are a friendly assistant for {company}.\n"
                f"{system_extra}\n\n"
                f"Ask one question at a time. Be warm and natural. Keep responses SHORT — this is a phone call.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n{end_call_rule}"
            )
        else:
            schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                      '  "name": null,\n  "phone": null,\n'
                      '  "notes": "fechas y horas preferidas, separadas por coma",\n'
                      '  "end_call": false\n}')
            return (
                f"Eres un asistente amigable de {company}. Responde siempre en español.\n"
                f"{system_extra}\n\n"
                f"Haz una pregunta a la vez. Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n{end_call_rule}"
            )

    # ── meeting_type (no questions, just name + callback number) ─
    if meeting_type or not questions:
        caller_num_hint = f" Their number appears to be {caller_fmt}." if caller_fmt else ""
        if lang == "en":
            schema = ('{\n  "message": "what to say aloud",\n  "name": "full name or null",\n'
                      '  "phone": "callback phone number or null",\n  "notes": null,\n'
                      '  "end_call": false\n}')
            return (
                f"You are a friendly pre-screening assistant for {company}.\n"
                f"{system_extra}\n"
                f"{caller_num_hint}\n\n"
                f"Start by greeting the caller and introducing yourself as an assistant from {company}.\n"
                f"Ask one question at a time. Be warm and natural. Keep responses SHORT — this is a phone call.\n"
                f"Once you have the caller's name and callback number:\n"
                f"  Step 4a — Read the info back and ask: 'Is that correct?'\n"
                f"  Step 4b — Only after they confirm (yes/correct), tell them to please hold while you connect them with a team member. Set end_call to true at that point.\n"
                f"Never announce the connection while still waiting for their confirmation.\n\n"
                f"Respond ONLY in valid JSON:\n{schema}\n\n{phone_format_rule}\n{end_call_rule}"
            )
        else:
            schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                      '  "name": "nombre completo o null",\n  "phone": "número de rellamada o null",\n'
                      '  "notes": null,\n  "end_call": false\n}')
            return (
                f"Eres un asistente amigable de pre-selección de {company}. Responde siempre en español.\n"
                f"{system_extra}\n"
                f"{caller_num_hint}\n\n"
                f"Comienza saludando al llamante e identificándote como asistente de {company}.\n"
                f"Haz una pregunta a la vez. Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n"
                f"Una vez que tengas el nombre y el número de rellamada:\n"
                f"  Paso 4a — Repite los datos y pregunta: '¿Es correcto?'\n"
                f"  Paso 4b — Solo cuando confirmen (sí/correcto), indícales que por favor esperen mientras les conectas con un asesor. Establece end_call en true en ese momento.\n"
                f"Nunca anuncies la transferencia mientras aún esperas su confirmación.\n\n"
                f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}\n{end_call_rule}"
            )

    # ── general topics — conversational pre-screening ──────────
    opening_question = questions[0] if questions else "How can I help you today?"
    if lang == "en":
        schema = ('{\n  "message": "what to say aloud",\n  "name": "full name or null",\n'
                  '  "phone": "phone number or null",\n  "notes": "summary of what the caller needs, or null",\n'
                  '  "end_call": false\n}')
        phone_instruction = (
            f"Ask: 'Is {caller_fmt} the best number to reach you, or would you prefer a different one?' "
            f"Record whichever number they confirm."
        ) if caller_fmt else "Ask for their callback phone number."
        return (
            f"You are a friendly pre-screening assistant for {company}.\n"
            f"Your goal is to collect the caller's name, phone number, and enough context for a specialist to help them.\n"
            f"{system_extra}\n\n"
            f"Start by greeting the caller and introducing yourself as an assistant from {company}.\n"
            f"Follow this sequence, one question at a time:\n"
            f"  Step 1 — Ask for their full name.\n"
            f"  Step 2 — {phone_instruction}\n"
            f"  Step 3 — Open with: '{opening_question}'\n"
            f"            Then ask up to 2 natural follow-up questions based on what they say — do NOT follow a fixed script.\n"
            f"            Adapt each question to their previous answer. Be conversational.\n"
            f"            Goal: give the specialist enough context. Stop when you have a clear picture.\n"
            f"  Step 4a — Briefly summarize what the caller told you and ask: 'Is that correct?'\n"
            f"  Step 4b — Only after they confirm (yes/correct), tell them to please hold while you connect them with a specialist. Set end_call to true.\n"
            f"Never announce the connection while still waiting for their confirmation.\n\n"
            f"Be warm and natural. Keep responses SHORT — this is a phone call.\n\n"
            f"Respond ONLY in valid JSON:\n{schema}\n\n{phone_format_rule}\n{end_call_rule}"
        )
    else:
        opening_question_es = questions[0] if questions else "¿En qué le puedo ayudar?"
        schema = ('{\n  "message": "lo que debes decir en voz alta (siempre en español)",\n'
                  '  "name": "nombre completo o null",\n  "phone": "número de teléfono o null",\n'
                  '  "notes": "resumen de lo que necesita el llamante, o null",\n  "end_call": false\n}')
        phone_instruction = (
            f"Pregunta: '¿El número {caller_fmt} es el mejor número para contactarle, o prefiere uno diferente?' "
            f"Registra el número que confirme."
        ) if caller_fmt else "Pide su número de teléfono de contacto."
        return (
            f"Eres un asistente amigable de preselección de {company}. Responde siempre en español.\n"
            f"Tu objetivo es recopilar el nombre, teléfono y suficiente contexto para que un especialista pueda ayudarle.\n"
            f"{system_extra}\n\n"
            f"Comienza saludando al llamante e identificándote como asistente de {company}.\n"
            f"Sigue esta secuencia, una pregunta a la vez:\n"
            f"  Paso 1 — Pedir nombre completo.\n"
            f"  Paso 2 — {phone_instruction}\n"
            f"  Paso 3 — Abre con: '{opening_question_es}'\n"
            f"            Luego haz hasta 2 preguntas de seguimiento naturales basadas en lo que diga — NO sigas un guión fijo.\n"
            f"            Adapta cada pregunta a su respuesta anterior. Sé conversacional.\n"
            f"            Objetivo: darle al especialista suficiente contexto. Para cuando tengas una imagen clara.\n"
            f"  Paso 4a — Resume brevemente lo que contó y pregunta: '¿Es correcto?'\n"
            f"  Paso 4b — Solo cuando confirmen (sí/correcto), indícales que por favor esperen mientras les conectas con un especialista. Establece end_call en true.\n"
            f"Nunca anuncies la transferencia mientras aún esperas su confirmación.\n\n"
            f"Sé cálido y natural. Mantén las respuestas CORTAS — es una llamada telefónica.\n\n"
            f"Responde SOLO en JSON válido:\n{schema}\n\n{phone_format_rule}\n{end_call_rule}"
        )
