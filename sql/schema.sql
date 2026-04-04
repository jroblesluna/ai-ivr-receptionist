-- Schema for the Twilio AI receptionist app.
-- Safe to run on existing databases (IF NOT EXISTS everywhere).

CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    id            TEXT PRIMARY KEY,
    datetime      TEXT,
    caller_number TEXT,
    caller_name   TEXT,
    topic         TEXT,
    language      TEXT
);

CREATE TABLE IF NOT EXISTS use_cases (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    industry    TEXT,
    url         TEXT,
    voice_en    TEXT,
    voice_es    TEXT,
    slogan_en   TEXT,
    slogan_es   TEXT
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    use_case_id     TEXT NOT NULL REFERENCES use_cases(id) ON DELETE CASCADE,
    key             TEXT NOT NULL,
    digit           TEXT,
    meeting_type    INTEGER DEFAULT 0,
    label_en        TEXT,
    label_es        TEXT,
    menu_text_en    TEXT,
    menu_text_es    TEXT,
    greeting_en     TEXT,
    greeting_es     TEXT,
    system_extra_en TEXT,
    system_extra_es TEXT,
    questions_en    TEXT DEFAULT '[]',
    questions_es    TEXT DEFAULT '[]',
    UNIQUE(use_case_id, key)
);
