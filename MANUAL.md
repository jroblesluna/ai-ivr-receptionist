# AI IVR Receptionist — User Manual

An AI-powered phone receptionist built with Twilio, Flask, and OpenAI. Handles inbound calls in English and Spanish, pre-screens callers conversationally, and connects them with a human operator.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Requirements](#2-requirements)
3. [Local Setup](#3-local-setup)
4. [Environment Variables](#4-environment-variables)
5. [Running Locally with ngrok](#5-running-locally-with-ngrok)
6. [Use Cases](#6-use-cases)
7. [Call Flow](#7-call-flow)
8. [Whitelist — Direct Transfer Numbers](#8-whitelist--direct-transfer-numbers)
9. [Email Reports](#9-email-reports)
10. [Production Deployment — Railway](#10-production-deployment--railway)
11. [Switching Use Cases](#11-switching-use-cases)
12. [Adding a New Use Case](#12-adding-a-new-use-case)

---

## 1. Architecture Overview

```
Caller → Twilio → Flask App (ngrok / Railway)
                       │
                       ├── Intro WAV + Menu (EN/ES)
                       ├── AI Conversation (OpenAI GPT-4o-mini)
                       ├── Operator Conference (Twilio Conference)
                       ├── Call Recording (Whisper transcription)
                       └── Email Report (Gmail SMTP)
```

**Key files:**

| File | Purpose |
|------|---------|
| `src/app.py` | Flask app entry point |
| `src/use_cases.json` | All industry use cases and topics |
| `src/use_case_loader.py` | Loads the active use case from env |
| `src/prompts.py` | Builds AI system prompts dynamically |
| `src/whitelist.json` | Direct-transfer phone numbers |
| `src/routes/menu.py` | IVR menu routes |
| `src/routes/ai.py` | AI conversation routes |
| `src/routes/operator.py` | Operator connection, recording, reports |
| `assets/` | Audio files (intro.wav, wait-music.wav) |

---

## 2. Requirements

- Python 3.11+
- ffmpeg (for audio channel splitting)
- A Twilio account with a phone number
- An OpenAI API key
- A Gmail account with an App Password (for email reports)

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install ffmpeg (macOS):

```bash
brew install ffmpeg
```

---

## 3. Local Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd twilio

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in environment variables
cp .env.example .env
# Edit .env with your credentials

# 4. Start the server
cd src && python app.py
```

The server runs on `http://localhost:5000`.

---

## 4. Environment Variables

Edit `.env` with the following values:

| Variable | Description | Example |
|----------|-------------|---------|
| `USE_CASE_ID` | Active use case | `robles_ai` |
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | `ACxxxxxxxx...` |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | `f9688...` |
| `TWILIO_NUMBER` | Your Twilio phone number | `+12012052544` |
| `FORWARD_TO` | Operator's phone number | `+16693002772` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-...` |
| `SMTP_HOST` | SMTP server | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | Gmail account (real login) | `jrobles@sistemas.com.pe` |
| `SMTP_PASSWORD` | Gmail App Password (16 chars) | `hramcwa...` |
| `SMTP_FROM` | Sender alias | `info@sistemas.com.pe` |
| `REPORT_EMAIL` | Report destination email | `antonio@robles.ai` |

---

## 5. Running Locally with ngrok

Twilio requires a public HTTPS URL to reach your local server.

```bash
# Important: specify the IPv4 address explicitly to avoid AirPlay conflicts on macOS
ngrok http 127.0.0.1:5000
```

Copy the `https://xxxx.ngrok-free.app` URL and set it in Twilio:

1. Go to [console.twilio.com](https://console.twilio.com)
2. Phone Numbers → Manage → Active Numbers → your number
3. Set **Voice webhook** (HTTP POST) to: `https://xxxx.ngrok-free.app/`

> **Note:** Each time you restart ngrok, the URL changes. In production, use a fixed URL (see section 10).

---

## 6. Use Cases

Available use cases (set `USE_CASE_ID` in `.env`):

| ID | Name | Industry |
|----|------|----------|
| `robles_ai` | Robles AI | Technology & Education |
| `sweet_crust` | Sweet Crust Bakery | Food and Beverage |
| `lex_partners` | Lex and Partners | Legal Services |
| `vita_clinic` | Vita Medical Clinic | Healthcare |
| `sol_realty` | Sol Realty Group | Real Estate |
| `chem_supply` | Chem Supply | Industrial Distribution |
| `nova_auto` | Nova Auto | Automotive Services |
| `grand_hotel` | Grand Hotel | Hospitality |
| `smile_dental` | Smile Dental | Dental Care |
| `flex_gym` | Flex Gym | Fitness and Wellness |
| `safe_guard` | Safe Guard Insurance | Insurance |
| `luma_academy` | Luma Academy | Education and Tutoring |
| `blue_star` | Blue Star Restaurant | Food Service |

Each use case has 4 menu options:

- **Option 1** — Schedule / Book / Appointment (direct to operator after name + phone)
- **Option 2** — Switch to Spanish (or English)
- **Option 3** — Specific service A (AI pre-screening)
- **Option 4** — Specific service B (AI pre-screening)
- **Option 5** — Customer Service (AI pre-screening)

---

## 7. Call Flow

```
1. Caller dials the Twilio number
2. intro.wav plays
3. "Thank you for calling [Company]..." + menu options
4. Caller presses a digit (or 2 for Spanish)
   │
   ├── Option 1 (meeting/booking):
   │     AI asks name → confirms phone → caller confirms → hold music
   │     → Operator receives briefing → joins conference
   │
   └── Options 3/4/5 (pre-screening):
         AI asks name → confirms phone → opening question
         → 2 conversational follow-up questions (adaptive)
         → AI summarizes and asks "Is that correct?"
         → Caller confirms → hold music
         → Operator receives briefing → joins conference

5. Operator answers briefing:
   "Incoming pre-screened call. Topic: [X]. Caller: [Name]. Phone: [Y]. Notes: [Z]."
   → Operator joins the conference with the caller

6. After the call:
   → Recording processed (Whisper transcription)
   → GPT summary generated
   → Full Call Report printed to console
   → Report emailed to REPORT_EMAIL
```

**If the operator does not answer:**
The caller is redirected to the AI for callback scheduling (`schedule_callback` topic).

---

## 8. Whitelist — Direct Transfer Numbers

Numbers in `src/whitelist.json` bypass the menu and go directly to the operator.

```json
["+14085900153", "+1XXXXXXXXXX"]
```

The operator receives a briefing: *"Direct transfer — whitelisted number."*

---

## 9. Email Reports

After each call, a report is emailed to `REPORT_EMAIL` with:

1. **AI ↔ Caller conversation** (full transcript)
2. **AI → Operator briefing** (what the AI told the operator)
3. **Caller ↔ Operator transcription** (Whisper, with speaker labels if dual-channel)
4. **GPT summary** (key points, agreements, next steps)
5. **Goodbye message** (last thing the AI said to the caller)

For callback requests (no operator available), a simpler email is sent with the caller's preferred callback times.

**Gmail App Password setup:**
1. Enable 2-Step Verification on your Google account
2. Go to myaccount.google.com → Security → App passwords
3. Create a new app password and paste it into `SMTP_PASSWORD` in `.env`

---

## 10. Production Deployment — Railway

**Recommended: [Railway](https://railway.app)** — always-on, free tier ($5 credit/month), simple GitHub deploy, custom domains.

### Deploy steps:

```bash
# 1. Push your code to GitHub (make sure .env is in .gitignore)
git push origin main

# 2. Go to railway.app → New Project → Deploy from GitHub repo

# 3. Set environment variables in Railway dashboard:
#    (same as your .env file — paste each one)

# 4. Railway auto-detects the Procfile and deploys

# 5. Get your public URL from Railway → Settings → Domains
#    Example: https://your-app.up.railway.app
```

### Custom subdomain:

1. In Railway → Settings → Domains → Add custom domain
2. Enter your subdomain: `ivr.sistemas.com.pe`
3. Add the CNAME record in your DNS provider:
   ```
   ivr.sistemas.com.pe  CNAME  your-app.up.railway.app
   ```
4. Update Twilio webhook to: `https://ivr.sistemas.com.pe/`

### Why Railway over others:

| Platform | Free tier | Always on | Custom domain | Ease |
|----------|-----------|-----------|---------------|------|
| **Railway** | $5/mo credit | Yes | Yes | Very easy |
| Render | 750h/mo | No (sleeps) | Yes | Easy |
| Fly.io | 3 VMs | Yes | Yes | Medium |
| Google Cloud Run | 2M req/mo | Configurable | Yes | Complex |
| Heroku | None (paid) | Yes | Yes | Easy |

> Render's free tier **sleeps after 15 minutes of inactivity** — bad for phone calls. Railway and Fly.io stay always on.

---

## 11. Switching Use Cases

To switch the active use case, update `USE_CASE_ID` in `.env`:

```bash
USE_CASE_ID=chem_supply
```

Restart the server. No code changes needed — everything (menu, greetings, prompts, company name) updates automatically.

---

## 12. Adding a New Use Case

Add a new entry to `src/use_cases.json` following this structure:

```json
"my_company": {
  "id": "my_company",
  "name": "My Company Name",
  "industry": "Industry Name",
  "topics": {
    "meeting": {
      "digit": "1",
      "meeting_type": true,
      "en": {
        "label": "Schedule a Meeting",
        "menu_text": "Press 1 to Schedule a Meeting.",
        "greeting": "Hi! I'm the My Company assistant...",
        "system_extra": "Context for the AI about this topic.",
        "questions": []
      },
      "es": {
        "label": "Agendar una Reunión",
        "menu_text": "Presione 1 para Agendar una Reunión.",
        "greeting": "¡Hola! Soy el asistente de My Company...",
        "system_extra": "Contexto para la IA sobre este tema.",
        "questions": []
      }
    },
    "topic_a": {
      "digit": "3",
      "meeting_type": false,
      "en": {
        "label": "Topic A",
        "menu_text": "Press 3 for Topic A.",
        "greeting": "Hi! What is your name?",
        "system_extra": "AI context for topic A.",
        "questions": ["Opening question for topic A?"]
      },
      "es": { ... }
    },
    "topic_b": { "digit": "4", ... },
    "customer_service": { "digit": "5", ... }
  }
}
```

**Rules:**
- `digit` must be unique within the use case (`1`, `3`, `4`, `5` — digit `2` is reserved for language toggle)
- `meeting_type: true` → AI only asks name + phone, no pre-screening questions
- `questions: []` with `meeting_type: false` → same behavior as `meeting_type: true`
- `questions: ["one question"]` → AI asks that question, then improvises 2 conversational follow-ups
- Set `USE_CASE_ID=my_company` in `.env` and restart

---

*Built with Twilio, OpenAI GPT-4o-mini, Whisper, Flask, and Google Neural2 TTS voices.*
