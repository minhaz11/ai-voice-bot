# Jannet — clinic voice receptionist

A simple browser voice bot with a Python/FastAPI backend and Gemini `gemini-3.1-flash-live-preview`. The interface follows the supplied screenshot. Audio goes through the backend; your API key stays on the server.

## Run

Requires Python 3.11+ and a browser with microphone access.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# .env is already prepared. Put your key in GEMINI_API_KEY.
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000, allow microphone access, and click **Call Jannet**. Voice changes in `GEMINI_VOICE` apply on the next call. Other `.env` changes require a server restart and page refresh. Use a Gemini voice name such as Sulafat (warm), Aoede (breezy), or Kore (firm); Nova is not a documented Gemini voice. Obtain a key with Live API access at https://aistudio.google.com/apikey. Do not paste the key into frontend code.

## Conversation

Jannet introduces herself as the doctor's AI assistant and asks why the patient is calling. She checks available times, reserves the selected slot, gently asks for the visit reason, patient name and phone number, reads all details back, and saves the appointment after an explicit confirmation. A persistent booking reference is shown with the patient name on the confirmation card. Jannet asks whether anything else is needed before ending the call. She says goodbye before audio and microphone stop. Callers can interrupt her or end the call manually. Temporary reservations are released on disconnect and expire after 15 minutes. Concurrent bookings cannot share a slot.

### Response latency

The live model is the single biggest factor. Measured end of caller speech to Jannet's first audio
byte, seven trials each with an open microphone: `gemini-3.1-flash-live-preview` ran a 1.45s median
with a 1.55s worst case, while `gemini-3.8-live` had a similar 1.56s median but wandered to 3.4s and
occasionally past 5s. The medians are close; the tail is what a caller hears as a dead line, so the
flash live model is the default. Switch `GEMINI_MODEL` back if you want 3.8-live's extra depth and
can tolerate the occasional pause.

The server logs every turn as `reply started N.NNs after the caller stopped`, and warns above 2.5s,
so a real call can be diagnosed from the uvicorn output. Timings only, never transcript text.

The live model will spend several seconds of internal deliberation per turn if you let it, which a
caller hears as dead air and reads as a frozen call — worst at the intake questions, where the
instructions branch most. `GEMINI_THINKING_BUDGET` defaults to `0` so Jannet answers in about a
second; raise it only if you want her to deliberate and can accept the silence. The page shows
"Jannet is thinking…" whenever she is composing, so a pause never looks like a hang.

Microphone activity detection is deliberately insensitive (`prefix_padding_ms` 300, low start/end
sensitivity) so speaker echo and room noise are not mistaken for the caller barging in. Interrupting
her out loud still works.

Defaults: Dr Emily Carter, 9am–5pm, 30-minute slots, Monday–Friday, Asia/Dhaka timezone, next 30 days. Change these and the voice in `.env`. `WEEKEND_DAYS` uses Monday=0 through Sunday=6. This allows changing weekends for your clinic.

Bookings are stored in `appointments.sqlite3`; this is a local schedule, with no Google Calendar or SMS integration. The screenshot's footer is a visual reference, not an instruction to connect an external calendar. No recording or transcript is saved; patient names, visit reasons, phone numbers and booking references are stored locally, and audio is sent to Google for processing. The transcript is visible only in the current page.

This is a local prototype. Before public patient use, add access controls, appropriate patient-data storage/retention policies, and a real clinic scheduling integration if needed. Use HTTPS for microphone access outside localhost. Do not expose this unauthenticated development server publicly.

## Verify

```bash
python -m pytest -q
```

Manual voice check after adding the key: Jannet greets first; ask for a weekend (she should offer a weekday); pick an available time; provide a reason and phone number; correct a detail during readback; confirm; verify the confirmation card and full goodbye. Try interruption and denied microphone permission. Actual voice quality and live model access require the API key and a real microphone.

Google documentation: https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
