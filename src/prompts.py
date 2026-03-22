from topics import TOPICS
from helpers import format_phone_spoken


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
