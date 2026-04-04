-- Seed data for use_cases and topics tables.
-- Generated from src/use_cases.json
-- Run after schema.sql on a fresh database.

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'robles_ai', 'Robles AI', 'Technology & Education', 'roblesai.com',
  'Google.en-GB-Neural2-F', 'Google.es-US-Standard-A',
  'AI technology powered by Silicon Valley, built for your future.', 'Tecnología de IA impulsada desde Silicon Valley, creada para su futuro.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'robles_ai', 'meeting', '1', 1,
  'Schedule a Meeting', 'Agendar una Reunión',
  'Press 1 to Schedule a Meeting with our team.', 'Presione 1 para Agendar una Reunión con nuestro equipo.',
  'Hi! I''m the Robles AI assistant. I''ll get your details so our team can reach out to you. Could I start with your name?', '¡Hola! Soy el asistente de Robles AI. Tomaré sus datos para que nuestro equipo le contacte. ¿Podría decirme su nombre?',
  'The caller wants to schedule a meeting. Ask for name and confirm callback number only.', 'El llamante desea agendar una reunión. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'robles_ai', 'ai_ml', '3', 0,
  'AI and Machine Learning', 'IA y Machine Learning',
  'Press 3 for Artificial Intelligence and Machine Learning.', 'Presione 3 para Inteligencia Artificial y Machine Learning.',
  'Hi! I''m the Robles AI assistant. I''ll take a couple of quick details to connect you with the right specialist. What is your name?', '¡Hola! Soy el asistente de Robles AI. Tomaré un par de datos para conectarle con el especialista correcto. ¿Cuál es su nombre?',
  'The caller is interested in AI and Machine Learning services.', 'El llamante está interesado en servicios de IA y Machine Learning.',
  '["What are you looking to build or improve with AI?"]', '["¿Qué desea construir o mejorar con IA?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'robles_ai', 'computer_vision', '4', 0,
  'Computer Vision', 'Visión por Computadora',
  'Press 4 for Computer Vision Services.', 'Presione 4 para Servicios de Visión por Computadora.',
  'Hi! I''m the Robles AI assistant. I''ll take a couple of quick details to connect you with the right specialist. What is your name?', '¡Hola! Soy el asistente de Robles AI. Tomaré un par de datos para conectarle con el especialista correcto. ¿Cuál es su nombre?',
  'The caller is interested in Computer Vision services.', 'El llamante está interesado en servicios de Visión por Computadora.',
  '["What do you need to detect or analyze visually?"]', '["¿Qué necesita detectar o analizar visualmente?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'robles_ai', 'customer_service', '5', 0,
  'Customer Service', 'Servicio al Cliente',
  'Press 5 for Customer Service.', 'Presione 5 para Servicio al Cliente.',
  'Hi! I''m the Robles AI customer service assistant. I''ll take your details to connect you with our team. What is your name?', '¡Hola! Soy el asistente de servicio al cliente de Robles AI. Tomaré sus datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller needs customer service support.', 'El llamante necesita soporte de servicio al cliente.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'sweet_crust', 'Sweet Crust Bakery', 'Food and Beverage', 'sweetcrustbakery.com',
  'Google.en-US-Neural2-F', 'Google.es-US-Neural2-A',
  'Baked with love, every single day.', 'Horneado con amor, cada día.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sweet_crust', 'meeting', '1', 0,
  'Order Status', 'Estado de Pedido',
  'Press 1 to check your Order Status.', 'Presione 1 para consultar el Estado de su Pedido.',
  'Hi! I''m the Sweet Crust Bakery assistant. I''ll look up your order right away. What is your order number?', '¡Hola! Soy el asistente de Sweet Crust Bakery. Consultaré su pedido de inmediato. ¿Cuál es su número de pedido?',
  'The caller wants to check the status of an existing order. Ask for their order number first (demo order number is 1234 — if they provide it, confirm it and let them know their order is being prepared and on schedule). Then get their name and phone.', 'El llamante desea consultar el estado de un pedido existente. Pida primero el número de pedido (para la demo, el número de pedido es 1234 — si lo proporciona, confírmelo e indique que el pedido está en preparación y en tiempo). Luego obtenga nombre y teléfono.',
  '["What is your order number?", "What is the name on the order?"]', '["¿Cuál es su número de pedido?", "¿A nombre de quién está el pedido?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sweet_crust', 'custom_cakes', '3', 0,
  'Custom Cakes and Pastries', 'Pasteles y Repostería',
  'Press 3 for Custom Cakes and Pastries.', 'Presione 3 para Pasteles y Repostería Personalizada.',
  'Hi! I''m the Sweet Crust Bakery assistant. I''d love to help you with a custom order. What is your name?', '¡Hola! Soy el asistente de Sweet Crust Bakery. Con gusto le ayudo con su pedido personalizado. ¿Cuál es su nombre?',
  'The caller wants to order a custom cake or pastry.', 'El llamante desea ordenar un pastel o repostería personalizada.',
  '["What type of cake or pastry are you looking for?"]', '["¿Qué tipo de pastel o repostería está buscando?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sweet_crust', 'catering', '4', 0,
  'Catering and Events', 'Catering y Eventos',
  'Press 4 for Catering and Events.', 'Presione 4 para Catering y Eventos.',
  'Hi! I''m the Sweet Crust Bakery assistant. I''ll gather some quick details about your event. What is your name?', '¡Hola! Soy el asistente de Sweet Crust Bakery. Tomaré algunos datos sobre su evento. ¿Cuál es su nombre?',
  'The caller is interested in catering services for an event.', 'El llamante está interesado en servicios de catering para un evento.',
  '["Tell me about your event — what is the occasion?"]', '["Cuénteme sobre su evento, ¿cuál es la ocasión?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sweet_crust', 'customer_service', '5', 0,
  'Customer Service', 'Servicio al Cliente',
  'Press 5 for Customer Service.', 'Presione 5 para Servicio al Cliente.',
  'Hi! I''m the Sweet Crust Bakery customer service assistant. What is your name?', '¡Hola! Soy el asistente de servicio al cliente de Sweet Crust Bakery. ¿Cuál es su nombre?',
  'The caller needs customer service assistance.', 'El llamante necesita asistencia de servicio al cliente.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'lex_partners', 'Lex and Partners', 'Legal Services', 'lexandpartners.com',
  'Google.en-US-Neural2-J', 'Google.es-US-Neural2-B',
  'Your rights, our mission.', 'Sus derechos, nuestra misión.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'lex_partners', 'meeting', '1', 1,
  'Schedule a Consultation', 'Agendar una Consulta',
  'Press 1 to Schedule a Legal Consultation.', 'Presione 1 para Agendar una Consulta Legal.',
  'Thank you for calling Lex and Partners. I''m the pre-screening assistant. May I have your name?', 'Gracias por llamar a Lex y Asociados. Soy el asistente de preselección. ¿Me podría indicar su nombre?',
  'The caller wants to schedule a legal consultation. Ask for name and confirm callback number only.', 'El llamante desea agendar una consulta legal. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'lex_partners', 'family_law', '3', 0,
  'Family Law', 'Derecho de Familia',
  'Press 3 for Family Law.', 'Presione 3 para Derecho de Familia.',
  'Thank you for calling Lex and Partners. I''m the pre-screening assistant for Family Law. What is your name?', 'Gracias por llamar a Lex y Asociados. Soy el asistente de preselección para Derecho de Familia. ¿Cuál es su nombre?',
  'The caller needs assistance with a family law matter.', 'El llamante necesita asistencia en un asunto de derecho de familia.',
  '["What type of family law matter can I help you with?"]', '["¿En qué asunto de derecho de familia puedo ayudarle?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'lex_partners', 'corporate_law', '4', 0,
  'Corporate Law', 'Derecho Corporativo',
  'Press 4 for Corporate and Business Law.', 'Presione 4 para Derecho Corporativo y Empresarial.',
  'Thank you for calling Lex and Partners. I''m the pre-screening assistant for Corporate Law. What is your name?', 'Gracias por llamar a Lex y Asociados. Soy el asistente de preselección para Derecho Corporativo. ¿Cuál es su nombre?',
  'The caller is inquiring about corporate or business law services.', 'El llamante consulta sobre servicios de derecho corporativo o empresarial.',
  '["What type of legal matter does your business need help with?"]', '["¿En qué tipo de asunto legal necesita ayuda su empresa?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'lex_partners', 'customer_service', '5', 0,
  'General Inquiries', 'Consultas Generales',
  'Press 5 for General Inquiries.', 'Presione 5 para Consultas Generales.',
  'Thank you for calling Lex and Partners. I''m here to help. What is your name?', 'Gracias por llamar a Lex y Asociados. Estoy aquí para ayudarle. ¿Cuál es su nombre?',
  'The caller has a general inquiry for the law firm.', 'El llamante tiene una consulta general para el bufete.',
  '["How can I help you today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'vita_clinic', 'Vita Medical Clinic', 'Healthcare', 'vitamedicalclinic.com',
  'Google.en-US-Neural2-C', 'Google.es-US-Neural2-A',
  'Your health is our priority.', 'Su salud es nuestra prioridad.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'vita_clinic', 'meeting', '1', 1,
  'Book an Appointment', 'Agendar una Cita',
  'Press 1 to Book an Appointment.', 'Presione 1 para Agendar una Cita.',
  'Thank you for calling Vita Medical Clinic. I''m the scheduling assistant. May I have your name?', 'Gracias por llamar a Clínica Médica Vita. Soy el asistente de agendado. ¿Me podría indicar su nombre?',
  'The caller wants to book a medical appointment. Ask for name and confirm callback number only.', 'El llamante desea agendar una cita médica. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'vita_clinic', 'general_medicine', '3', 0,
  'General Medicine', 'Medicina General',
  'Press 3 for General Medicine.', 'Presione 3 para Medicina General.',
  'Thank you for calling Vita Medical Clinic. I''m the pre-screening assistant for General Medicine. What is your name?', 'Gracias por llamar a Clínica Médica Vita. Soy el asistente de preselección para Medicina General. ¿Cuál es su nombre?',
  'The caller needs a general medicine consultation.', 'El llamante necesita una consulta de medicina general.',
  '["What brings you in today?"]', '["¿Cuál es el motivo de su consulta hoy?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'vita_clinic', 'pediatrics', '4', 0,
  'Pediatrics', 'Pediatría',
  'Press 4 for Pediatrics.', 'Presione 4 para Pediatría.',
  'Thank you for calling Vita Medical Clinic. I''m the pre-screening assistant for Pediatrics. What is your name?', 'Gracias por llamar a Clínica Médica Vita. Soy el asistente de preselección para Pediatría. ¿Cuál es su nombre?',
  'The caller needs pediatric care for a child.', 'El llamante necesita atención pediátrica para un niño.',
  '["What brings you in for the little one today?"]', '["¿Cuál es el motivo de la consulta para el niño hoy?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'vita_clinic', 'customer_service', '5', 0,
  'Patient Services', 'Servicios al Paciente',
  'Press 5 for Patient Services.', 'Presione 5 para Servicios al Paciente.',
  'Thank you for calling Vita Medical Clinic. I''m here to assist you. What is your name?', 'Gracias por llamar a Clínica Médica Vita. Estoy aquí para ayudarle. ¿Cuál es su nombre?',
  'The caller has a patient services inquiry.', 'El llamante tiene una consulta de servicios al paciente.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'sol_realty', 'Sol Realty Group', 'Real Estate', 'solrealtygroup.com',
  'Google.en-US-Neural2-H', 'Google.es-US-Neural2-A',
  'Finding the perfect place to call home.', 'Encontrando el lugar perfecto para llamar hogar.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sol_realty', 'meeting', '1', 1,
  'Schedule a Property Viewing', 'Agendar una Visita',
  'Press 1 to Schedule a Property Viewing.', 'Presione 1 para Agendar una Visita a Propiedad.',
  'Hi! I''m the Sol Realty Group assistant. I''ll get your details so one of our agents can reach out right away. What is your name?', '¡Hola! Soy el asistente de Sol Realty Group. Tomaré sus datos para que uno de nuestros agentes le contacte de inmediato. ¿Cuál es su nombre?',
  'The caller wants to schedule a property viewing. Ask for name and confirm callback number only.', 'El llamante desea agendar una visita a una propiedad. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sol_realty', 'buy_property', '3', 0,
  'Buy a Property', 'Comprar una Propiedad',
  'Press 3 to Buy a Property.', 'Presione 3 para Comprar una Propiedad.',
  'Hi! I''m the Sol Realty Group assistant. I''ll take a couple of details to connect you with the right agent. What is your name?', '¡Hola! Soy el asistente de Sol Realty Group. Tomaré un par de datos para conectarle con el agente correcto. ¿Cuál es su nombre?',
  'The caller is interested in buying a property.', 'El llamante está interesado en comprar una propiedad.',
  '["What type of property are you looking for?"]', '["¿Qué tipo de propiedad está buscando?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sol_realty', 'sell_property', '4', 0,
  'Sell a Property', 'Vender una Propiedad',
  'Press 4 to Sell a Property.', 'Presione 4 para Vender una Propiedad.',
  'Hi! I''m the Sol Realty Group assistant. I''ll gather a couple of quick details to connect you with one of our agents. What is your name?', '¡Hola! Soy el asistente de Sol Realty Group. Tomaré un par de datos para conectarle con uno de nuestros agentes. ¿Cuál es su nombre?',
  'The caller is looking to sell a property.', 'El llamante desea vender una propiedad.',
  '["Tell me about the property you would like to sell."]', '["Cuénteme sobre la propiedad que desea vender."]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'sol_realty', 'customer_service', '5', 0,
  'Client Services', 'Servicios al Cliente',
  'Press 5 for Client Services.', 'Presione 5 para Servicios al Cliente.',
  'Hi! I''m the Sol Realty Group client services assistant. What is your name?', '¡Hola! Soy el asistente de servicios al cliente de Sol Realty Group. ¿Cuál es su nombre?',
  'The caller has a client services inquiry.', 'El llamante tiene una consulta de servicios al cliente.',
  '["How can I help you today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'chem_supply', 'Chem Supply', 'Industrial Distribution', 'chemsupply.com',
  'Google.en-US-Neural2-I', 'Google.es-US-Neural2-C',
  'Quality supplies, delivered on time.', 'Suministros de calidad, entregados a tiempo.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'chem_supply', 'meeting', '1', 1,
  'Schedule a Consultation', 'Agendar una Consulta',
  'Press 1 to Schedule a Sales Consultation.', 'Presione 1 para Agendar una Consulta de Ventas.',
  'Thank you for calling Chem Supply. I''m the sales assistant. I''ll get your details so our team can reach out to you. What is your name?', 'Gracias por llamar a Chem Supply. Soy el asistente de ventas. Tomaré sus datos para que nuestro equipo le contacte. ¿Cuál es su nombre?',
  'The caller wants to schedule a sales consultation. Ask for name and confirm callback number only.', 'El llamante desea agendar una consulta de ventas. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'chem_supply', 'product_catalog', '3', 0,
  'Product Catalog', 'Catálogo de Productos',
  'Press 3 for Product Catalog and Availability.', 'Presione 3 para Catálogo de Productos y Disponibilidad.',
  'Thank you for calling Chem Supply. I''m the product assistant. I''ll take a few details to connect you with our team. What is your name?', 'Gracias por llamar a Chem Supply. Soy el asistente de productos. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is inquiring about available products, specifications, or pricing.', 'El llamante consulta sobre productos disponibles, especificaciones o precios.',
  '["Which product or chemical compound are you looking for?"]', '["¿Qué producto o compuesto químico está buscando?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'chem_supply', 'bulk_orders', '4', 0,
  'Bulk Orders', 'Pedidos al por Mayor',
  'Press 4 for Bulk Orders and Wholesale.', 'Presione 4 para Pedidos al por Mayor.',
  'Thank you for calling Chem Supply. I''m the wholesale assistant. I''ll take a few details to connect you with our bulk sales team. What is your name?', 'Gracias por llamar a Chem Supply. Soy el asistente de ventas mayoristas. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in placing a bulk or wholesale order.', 'El llamante está interesado en realizar un pedido al por mayor.',
  '["What products and approximate quantities are you looking to order?"]', '["¿Qué productos y en qué cantidades aproximadas desea ordenar?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'chem_supply', 'customer_service', '5', 0,
  'Customer Service', 'Servicio al Cliente',
  'Press 5 for Customer Service.', 'Presione 5 para Servicio al Cliente.',
  'Thank you for calling Chem Supply. I''m the customer service assistant. What is your name?', 'Gracias por llamar a Chem Supply. Soy el asistente de servicio al cliente. ¿Cuál es su nombre?',
  'The caller needs customer service support — order tracking, returns, billing, or technical questions.', 'El llamante necesita soporte — seguimiento de pedidos, devoluciones, facturación o consultas técnicas.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'nova_auto', 'Nova Auto', 'Automotive Services', 'novaauto.com',
  'Google.en-US-Neural2-D', 'Google.es-US-Neural2-B',
  'Keeping you safely on the road.', 'Manteniéndole seguro en la carretera.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'nova_auto', 'meeting', '1', 1,
  'Schedule a Service', 'Agendar un Servicio',
  'Press 1 to Schedule a Vehicle Service.', 'Presione 1 para Agendar un Servicio de Vehículo.',
  'Hi! I''m the Nova Auto assistant. I''ll get your details to book your service appointment. What is your name?', '¡Hola! Soy el asistente de Nova Auto. Tomaré sus datos para reservar su cita de servicio. ¿Cuál es su nombre?',
  'The caller wants to schedule a vehicle service appointment. Ask for name and confirm callback number only.', 'El llamante desea agendar una cita de servicio vehicular. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'nova_auto', 'diagnostics', '3', 0,
  'Diagnostics and Repair', 'Diagnóstico y Reparación',
  'Press 3 for Diagnostics and Repair.', 'Presione 3 para Diagnóstico y Reparación.',
  'Hi! I''m the Nova Auto assistant for diagnostics and repair. I''ll take a few details to connect you with our technicians. What is your name?', '¡Hola! Soy el asistente de Nova Auto para diagnóstico y reparación. Tomaré algunos datos para conectarle con nuestros técnicos. ¿Cuál es su nombre?',
  'The caller needs vehicle diagnostics or repair service.', 'El llamante necesita servicio de diagnóstico o reparación vehicular.',
  '["What problem or symptom is your vehicle experiencing?"]', '["¿Qué problema o síntoma está presentando su vehículo?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'nova_auto', 'maintenance', '4', 0,
  'Preventive Maintenance', 'Mantenimiento Preventivo',
  'Press 4 for Preventive Maintenance.', 'Presione 4 para Mantenimiento Preventivo.',
  'Hi! I''m the Nova Auto maintenance assistant. I''ll take a few details to set up your maintenance plan. What is your name?', '¡Hola! Soy el asistente de mantenimiento de Nova Auto. Tomaré algunos datos para programar su plan de mantenimiento. ¿Cuál es su nombre?',
  'The caller is interested in preventive maintenance services.', 'El llamante está interesado en servicios de mantenimiento preventivo.',
  '["What type of maintenance does your vehicle need?"]', '["¿Qué tipo de mantenimiento necesita su vehículo?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'nova_auto', 'customer_service', '5', 0,
  'Customer Service', 'Servicio al Cliente',
  'Press 5 for Customer Service.', 'Presione 5 para Servicio al Cliente.',
  'Hi! I''m the Nova Auto customer service assistant. What is your name?', '¡Hola! Soy el asistente de servicio al cliente de Nova Auto. ¿Cuál es su nombre?',
  'The caller needs customer service support.', 'El llamante necesita soporte de servicio al cliente.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'grand_hotel', 'Grand Hotel', 'Hospitality', 'grandhotel.com',
  'Google.en-US-Neural2-G', 'Google.es-US-Neural2-A',
  'Where comfort meets elegance.', 'Donde el confort se encuentra con la elegancia.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'grand_hotel', 'meeting', '1', 1,
  'Book a Room', 'Reservar una Habitación',
  'Press 1 to Book a Room.', 'Presione 1 para Reservar una Habitación.',
  'Thank you for calling Grand Hotel. I''m the reservations assistant. I''ll get your details so our team can assist you. What is your name?', 'Gracias por llamar al Grand Hotel. Soy el asistente de reservaciones. Tomaré sus datos para que nuestro equipo le asista. ¿Cuál es su nombre?',
  'The caller wants to book a hotel room. Ask for name and confirm callback number only.', 'El llamante desea reservar una habitación. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'grand_hotel', 'events', '3', 0,
  'Events and Banquets', 'Eventos y Banquetes',
  'Press 3 for Events and Banquets.', 'Presione 3 para Eventos y Banquetes.',
  'Thank you for calling Grand Hotel. I''m the events assistant. I''ll take a few details to connect you with our events team. What is your name?', 'Gracias por llamar al Grand Hotel. Soy el asistente de eventos. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in booking a venue for an event or banquet.', 'El llamante está interesado en reservar un espacio para un evento o banquete.',
  '["Tell me about your event — what is the occasion and how many guests are you expecting?"]', '["Cuénteme sobre su evento — ¿cuál es la ocasión y cuántos invitados espera?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'grand_hotel', 'concierge', '4', 0,
  'Concierge Services', 'Servicios de Conserjería',
  'Press 4 for Concierge Services.', 'Presione 4 para Servicios de Conserjería.',
  'Thank you for calling Grand Hotel. I''m the concierge assistant. I''ll take a few details to help you. What is your name?', 'Gracias por llamar al Grand Hotel. Soy el asistente de conserjería. Tomaré algunos datos para ayudarle. ¿Cuál es su nombre?',
  'The caller needs concierge services — transportation, tours, restaurant reservations, or special requests.', 'El llamante necesita servicios de conserjería — transporte, tours, reservaciones de restaurante o solicitudes especiales.',
  '["What service or arrangement can I help you with?"]', '["¿En qué servicio o arreglo puedo ayudarle?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'grand_hotel', 'customer_service', '5', 0,
  'Guest Services', 'Servicios al Huésped',
  'Press 5 for Guest Services.', 'Presione 5 para Servicios al Huésped.',
  'Thank you for calling Grand Hotel. I''m the guest services assistant. What is your name?', 'Gracias por llamar al Grand Hotel. Soy el asistente de servicios al huésped. ¿Cuál es su nombre?',
  'The caller needs guest services support.', 'El llamante necesita soporte de servicios al huésped.',
  '["How can I assist you today?"]', '["¿En qué puedo asistirle hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'smile_dental', 'Smile Dental', 'Dental Care', 'smiledental.com',
  'Google.en-US-Neural2-F', 'Google.es-US-Neural2-A',
  'Healthy smiles, happy lives.', 'Sonrisas saludables, vidas felices.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'smile_dental', 'meeting', '1', 1,
  'Book an Appointment', 'Agendar una Cita',
  'Press 1 to Book a Dental Appointment.', 'Presione 1 para Agendar una Cita Dental.',
  'Thank you for calling Smile Dental. I''m the scheduling assistant. May I have your name?', 'Gracias por llamar a Smile Dental. Soy el asistente de agendado. ¿Me podría indicar su nombre?',
  'The caller wants to book a dental appointment. Ask for name and confirm callback number only.', 'El llamante desea agendar una cita dental. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'smile_dental', 'general_dentistry', '3', 0,
  'General Dentistry', 'Odontología General',
  'Press 3 for General Dentistry.', 'Presione 3 para Odontología General.',
  'Thank you for calling Smile Dental. I''m the pre-screening assistant for General Dentistry. What is your name?', 'Gracias por llamar a Smile Dental. Soy el asistente de preselección para Odontología General. ¿Cuál es su nombre?',
  'The caller needs general dental care.', 'El llamante necesita atención dental general.',
  '["What brings you to the dentist today?"]', '["¿Cuál es el motivo de su visita al dentista hoy?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'smile_dental', 'cosmetic_dentistry', '4', 0,
  'Cosmetic Dentistry', 'Odontología Estética',
  'Press 4 for Cosmetic Dentistry.', 'Presione 4 para Odontología Estética.',
  'Thank you for calling Smile Dental. I''m the pre-screening assistant for Cosmetic Dentistry. What is your name?', 'Gracias por llamar a Smile Dental. Soy el asistente de preselección para Odontología Estética. ¿Cuál es su nombre?',
  'The caller is interested in cosmetic dental treatments.', 'El llamante está interesado en tratamientos dentales estéticos.',
  '["What cosmetic treatment are you interested in?"]', '["¿En qué tratamiento estético está interesado?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'smile_dental', 'customer_service', '5', 0,
  'Patient Services', 'Servicios al Paciente',
  'Press 5 for Patient Services.', 'Presione 5 para Servicios al Paciente.',
  'Thank you for calling Smile Dental. I''m here to assist you. What is your name?', 'Gracias por llamar a Smile Dental. Estoy aquí para ayudarle. ¿Cuál es su nombre?',
  'The caller has a patient services inquiry.', 'El llamante tiene una consulta de servicios al paciente.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'flex_gym', 'Flex Gym', 'Fitness and Wellness', 'flexgym.com',
  'Google.en-US-Neural2-I', 'Google.es-US-Neural2-C',
  'Train harder, live better.', 'Entrena más fuerte, vive mejor.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'flex_gym', 'meeting', '1', 1,
  'Membership Information', 'Información de Membresía',
  'Press 1 for Membership Information.', 'Presione 1 para Información de Membresía.',
  'Hi! I''m the Flex Gym assistant. I''ll get your details so our team can walk you through our membership options. What is your name?', '¡Hola! Soy el asistente de Flex Gym. Tomaré sus datos para que nuestro equipo le explique las opciones de membresía. ¿Cuál es su nombre?',
  'The caller wants information about gym memberships. Ask for name and confirm callback number only.', 'El llamante quiere información sobre membresías del gimnasio. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'flex_gym', 'personal_training', '3', 0,
  'Personal Training', 'Entrenamiento Personal',
  'Press 3 for Personal Training.', 'Presione 3 para Entrenamiento Personal.',
  'Hi! I''m the Flex Gym assistant for Personal Training. I''ll take a few details to connect you with our trainers. What is your name?', '¡Hola! Soy el asistente de Flex Gym para Entrenamiento Personal. Tomaré algunos datos para conectarle con nuestros entrenadores. ¿Cuál es su nombre?',
  'The caller is interested in personal training sessions.', 'El llamante está interesado en sesiones de entrenamiento personal.',
  '["What are your main fitness goals?"]', '["¿Cuáles son sus principales objetivos de fitness?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'flex_gym', 'group_classes', '4', 0,
  'Group Classes', 'Clases Grupales',
  'Press 4 for Group Classes.', 'Presione 4 para Clases Grupales.',
  'Hi! I''m the Flex Gym assistant for Group Classes. I''ll take a few details to connect you with our team. What is your name?', '¡Hola! Soy el asistente de Flex Gym para Clases Grupales. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in group fitness classes.', 'El llamante está interesado en clases de fitness grupales.',
  '["What type of group class are you interested in?"]', '["¿En qué tipo de clase grupal está interesado?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'flex_gym', 'customer_service', '5', 0,
  'Member Services', 'Servicios al Miembro',
  'Press 5 for Member Services.', 'Presione 5 para Servicios al Miembro.',
  'Hi! I''m the Flex Gym member services assistant. What is your name?', '¡Hola! Soy el asistente de servicios al miembro de Flex Gym. ¿Cuál es su nombre?',
  'The caller needs member services support.', 'El llamante necesita soporte de servicios al miembro.',
  '["How can I help you today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'safe_guard', 'Safe Guard Insurance', 'Insurance', 'safeguardinsurance.com',
  'Google.en-US-Neural2-D', 'Google.es-US-Neural2-B',
  'Protection you can always count on.', 'Protección en la que siempre puede confiar.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'safe_guard', 'meeting', '1', 1,
  'Schedule a Consultation', 'Agendar una Consulta',
  'Press 1 to Schedule an Insurance Consultation.', 'Presione 1 para Agendar una Consulta de Seguros.',
  'Thank you for calling Safe Guard Insurance. I''m the pre-screening assistant. I''ll get your details so an agent can reach out. What is your name?', 'Gracias por llamar a Safe Guard Insurance. Soy el asistente de preselección. Tomaré sus datos para que un agente le contacte. ¿Cuál es su nombre?',
  'The caller wants to schedule an insurance consultation. Ask for name and confirm callback number only.', 'El llamante desea agendar una consulta de seguros. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'safe_guard', 'auto_insurance', '3', 0,
  'Auto Insurance', 'Seguro de Auto',
  'Press 3 for Auto Insurance.', 'Presione 3 para Seguro de Auto.',
  'Thank you for calling Safe Guard Insurance. I''m the pre-screening assistant for Auto Insurance. What is your name?', 'Gracias por llamar a Safe Guard Insurance. Soy el asistente de preselección para Seguro de Auto. ¿Cuál es su nombre?',
  'The caller is inquiring about auto insurance coverage.', 'El llamante consulta sobre cobertura de seguro de auto.',
  '["Are you looking for a new policy, or do you need to update an existing one?"]', '["¿Está buscando una póliza nueva o necesita actualizar una existente?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'safe_guard', 'home_insurance', '4', 0,
  'Home Insurance', 'Seguro de Hogar',
  'Press 4 for Home Insurance.', 'Presione 4 para Seguro de Hogar.',
  'Thank you for calling Safe Guard Insurance. I''m the pre-screening assistant for Home Insurance. What is your name?', 'Gracias por llamar a Safe Guard Insurance. Soy el asistente de preselección para Seguro de Hogar. ¿Cuál es su nombre?',
  'The caller is inquiring about home or property insurance.', 'El llamante consulta sobre seguro de hogar o propiedad.',
  '["Are you looking to insure a new property, or do you need to update your current coverage?"]', '["¿Desea asegurar una nueva propiedad o actualizar su cobertura actual?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'safe_guard', 'customer_service', '5', 0,
  'Claims and Support', 'Reclamos y Soporte',
  'Press 5 for Claims and Support.', 'Presione 5 para Reclamos y Soporte.',
  'Thank you for calling Safe Guard Insurance. I''m the support assistant. What is your name?', 'Gracias por llamar a Safe Guard Insurance. Soy el asistente de soporte. ¿Cuál es su nombre?',
  'The caller needs claims support or general assistance.', 'El llamante necesita soporte de reclamos o asistencia general.',
  '["What can I help you with today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'luma_academy', 'Luma Academy', 'Education and Tutoring', 'lumaacademy.com',
  'Google.en-US-Neural2-C', 'Google.es-US-Neural2-A',
  'Illuminate your potential.', 'Ilumina tu potencial.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'luma_academy', 'meeting', '1', 1,
  'Schedule an Assessment', 'Agendar una Evaluación',
  'Press 1 to Schedule a Free Assessment.', 'Presione 1 para Agendar una Evaluación Gratuita.',
  'Hi! I''m the Luma Academy assistant. I''ll get your details so our team can schedule a free assessment. What is your name?', '¡Hola! Soy el asistente de Luma Academy. Tomaré sus datos para que nuestro equipo programe una evaluación gratuita. ¿Cuál es su nombre?',
  'The caller wants to schedule a free academic assessment. Ask for name and confirm callback number only.', 'El llamante desea agendar una evaluación académica gratuita. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'luma_academy', 'k12_tutoring', '3', 0,
  'K-12 Tutoring', 'Tutoría Escolar',
  'Press 3 for K-12 Tutoring.', 'Presione 3 para Tutoría Escolar.',
  'Hi! I''m the Luma Academy assistant for K-12 Tutoring. I''ll take a few details to connect you with our academic team. What is your name?', '¡Hola! Soy el asistente de Luma Academy para Tutoría Escolar. Tomaré algunos datos para conectarle con nuestro equipo académico. ¿Cuál es su nombre?',
  'The caller is inquiring about tutoring services for K-12 students.', 'El llamante consulta sobre servicios de tutoría para estudiantes de primaria y secundaria.',
  '["What grade level and subject does the student need help with?"]', '["¿En qué grado y materia necesita ayuda el estudiante?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'luma_academy', 'college_prep', '4', 0,
  'College Preparation', 'Preparación Universitaria',
  'Press 4 for College Preparation.', 'Presione 4 para Preparación Universitaria.',
  'Hi! I''m the Luma Academy assistant for College Preparation. I''ll take a few details to connect you with our team. What is your name?', '¡Hola! Soy el asistente de Luma Academy para Preparación Universitaria. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in college preparation programs — SAT, ACT, college essays, or admissions guidance.', 'El llamante está interesado en programas de preparación universitaria — SAT, ACT, ensayos universitarios u orientación de admisiones.',
  '["What aspect of college preparation are you focused on?"]', '["¿En qué aspecto de la preparación universitaria está enfocado?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'luma_academy', 'customer_service', '5', 0,
  'Student Services', 'Servicios al Estudiante',
  'Press 5 for Student Services.', 'Presione 5 para Servicios al Estudiante.',
  'Hi! I''m the Luma Academy student services assistant. What is your name?', '¡Hola! Soy el asistente de servicios al estudiante de Luma Academy. ¿Cuál es su nombre?',
  'The caller needs student or parent services support.', 'El llamante necesita soporte de servicios al estudiante o padre de familia.',
  '["How can I help you today?"]', '["¿En qué le puedo ayudar hoy?"]'
);

INSERT OR IGNORE INTO use_cases (id, name, industry, url, voice_en, voice_es, slogan_en, slogan_es) VALUES (
  'blue_star', 'Blue Star Restaurant', 'Food Service', 'bluestarrestaurant.com',
  'Google.en-US-Neural2-F', 'Google.es-US-Neural2-A',
  'Exceptional food, unforgettable moments.', 'Comida excepcional, momentos inolvidables.'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'blue_star', 'meeting', '1', 1,
  'Make a Reservation', 'Hacer una Reservación',
  'Press 1 to Make a Reservation.', 'Presione 1 para Hacer una Reservación.',
  'Thank you for calling Blue Star Restaurant. I''m the reservations assistant. I''ll get your details so our team can confirm your table. What is your name?', 'Gracias por llamar al Restaurante Blue Star. Soy el asistente de reservaciones. Tomaré sus datos para confirmar su mesa. ¿Cuál es su nombre?',
  'The caller wants to make a dining reservation. Ask for name and confirm callback number only.', 'El llamante desea hacer una reservación para cenar. Pida nombre y confirme el número de rellamada.',
  '[]', '[]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'blue_star', 'private_events', '3', 0,
  'Private Events', 'Eventos Privados',
  'Press 3 for Private Events.', 'Presione 3 para Eventos Privados.',
  'Thank you for calling Blue Star Restaurant. I''m the events assistant. I''ll take a few details to connect you with our events team. What is your name?', 'Gracias por llamar al Restaurante Blue Star. Soy el asistente de eventos. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in booking the restaurant for a private event.', 'El llamante está interesado en reservar el restaurante para un evento privado.',
  '["Tell me about your event — what is the occasion and how many guests are you expecting?"]', '["Cuénteme sobre su evento — ¿cuál es la ocasión y cuántos invitados espera?"]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'blue_star', 'catering', '4', 0,
  'Catering Services', 'Servicio de Catering',
  'Press 4 for Catering Services.', 'Presione 4 para Servicio de Catering.',
  'Thank you for calling Blue Star Restaurant. I''m the catering assistant. I''ll take a few details to connect you with our team. What is your name?', 'Gracias por llamar al Restaurante Blue Star. Soy el asistente de catering. Tomaré algunos datos para conectarle con nuestro equipo. ¿Cuál es su nombre?',
  'The caller is interested in catering services for an external event.', 'El llamante está interesado en servicios de catering para un evento externo.',
  '["Tell me about the event you need catering for."]', '["Cuénteme sobre el evento para el que necesita catering."]'
);

INSERT OR IGNORE INTO topics (use_case_id, key, digit, meeting_type, label_en, label_es, menu_text_en, menu_text_es, greeting_en, greeting_es, system_extra_en, system_extra_es, questions_en, questions_es) VALUES (
  'blue_star', 'customer_service', '5', 0,
  'Customer Service', 'Servicio al Cliente',
  'Press 5 for Customer Service.', 'Presione 5 para Servicio al Cliente.',
  'Thank you for calling Blue Star Restaurant. I''m here to assist you. What is your name?', 'Gracias por llamar al Restaurante Blue Star. Estoy aquí para ayudarle. ¿Cuál es su nombre?',
  'The caller needs customer service assistance.', 'El llamante necesita asistencia de servicio al cliente.',
  '["How can I help you today?"]', '["¿En qué le puedo ayudar hoy?"]'
);
