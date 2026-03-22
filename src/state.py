conversation_store = {}  # {call_sid: [{"role": ..., "content": ...}]}
collected_info     = {}  # {call_sid: {"name": None, "phone": None, "notes": None, "topic": "", "lang": ""}}
outbound_calls     = {}  # {room: outbound_call_sid} — para cancelar si el caller cuelga
failed_rooms       = set()  # rooms donde el agente no contestó → waitUrl redirige a IA
briefed_rooms      = set()  # rooms donde el operador sí contestó (operator-briefing fue llamado)
