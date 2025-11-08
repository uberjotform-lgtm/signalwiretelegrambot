import os
import re
import requests
from flask import Flask, request
from twilio.rest import Client as TwilioClient
from urllib.parse import urljoin

app = Flask(__name__)

# =========================
#   متغيرات البيئة (Render)
# =========================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER      = os.getenv("TWILIO_NUMBER")      # مثال: +1415xxxxxxx (رقم Twilio)
TG_TOKEN           = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID         = os.getenv("TELEGRAM_CHAT_ID")

TG_API = f"https://api.telegram.org/bot{TG_TOKEN}" if TG_TOKEN else ""

# تحويل أرقام عربية لإنجليزية
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def send_tg(text: str):
    try:
        if TG_API and TG_CHAT_ID:
            requests.post(f"{TG_API}/sendMessage",
                          data={"chat_id": TG_CHAT_ID, "text": text})
    except Exception:
        pass

def to_e164(user_input: str, default_cc="+20"):
    """
    يطبع الرقم لصيغة E.164:
    - يشيل مسافات/شرطات/أقواس
    - يحوّل أرقام عربية لإنجليزية
    - يتعامل مع + / 00 / 0 المحلية (لمصر +20 كافتراضي)
    """
    if not user_input:
        return None
    s = (user_input or "").strip().translate(AR_DIGITS)
    s = re.sub(r"[^\d+]", "", s)

    if s.startswith("+"):
        return s
    if s.startswith("00"):
        return "+" + s[2:]
    if s.startswith("0"):
        return default_cc + s[1:]
    if re.fullmatch(r"\d+", s):
        return default_cc + s
    return None

def missing_env():
    req = {
        "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
        "TWILIO_NUMBER": TWILIO_NUMBER,
        "TELEGRAM_BOT_TOKEN": TG_TOKEN,
        "TELEGRAM_CHAT_ID": TG_CHAT_ID,
    }
    return [k for k, v in req.items() if not v]

def twilio():
    return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.route("/")
def home():
    miss = missing_env()
    if miss:
        return f"Running, but missing env vars: {', '.join(miss)}", 500
    return "Twilio + Telegram Bot is Running ✅", 200

# =========================
#   Webhook تيليجرام
# =========================
@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    miss = missing_env()
    if miss:
        return f"Missing env vars: {', '.join(miss)}", 500

    upd = request.get_json(silent=True) or {}
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip()

    if not text:
        return "ok"

    if text.lower() in ("/start", "/ping"):
        send_tg("البوت شغال ✅\nاكتب: /call 01xxxxxxxxx أو /call +2010xxxxxxx")
        return "ok"

    # /call <number>
    if text.lower().startswith("/call"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_tg("📞 اكتب بالشكل: /call 01xxxxxxxxx أو /call +2010xxxxxxx")
            return "ok"

        raw = parts[1]
        to_number = to_e164(raw, default_cc="+20")  # غيّر +20 لو محتاج بلد افتراضية أخرى
        if not to_number or not to_number.startswith("+"):
            send_tg(f"❌ الرقم غير صحيح: {raw}\nجرّب بالشكل: +2010xxxxxxx أو 01xxxxxxxxx")
            return "ok"

        base = request.host_url  # مثل https://your-app.onrender.com/
        voice_url      = urljoin(base, "voice/outbound-start")
        status_cb_url  = urljoin(base, "voice/status")

        try:
            call = twilio().calls.create(
                from_=TWILIO_NUMBER,
                to=to_number,
                url=voice_url,                       # TwiML لبداية المكالمة
                method="POST",                       # نستخدم POST
                status_callback=status_cb_url,       # إشعارات الحالة
                status_callback_method="POST",
                status_callback_event=["initiated", "ringing", "answered", "completed"]
            )
            send_tg(f"📤 بدء مكالمة مع {to_number}\nCallSid: {call.sid}")
        except Exception as e:
            send_tg(f"❌ فشل بدء المكالمة: {e}")
        return "ok"

    return "ok"

# =========================
#   تدفق المكالمة (TwiML)
# =========================
@app.route("/voice/outbound-start", methods=["POST"])
def outbound_start():
    base = request.host_url
    gather_url = urljoin(base, "voice/gather")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="ar-EG">مرحبًا، شكرًا لاتصالك. اضغط واحد لرسالة النادي، أو اثنين لرسالة الشركة.</Say>
  <Gather input="dtmf speech" timeout="5" numDigits="1" action="{gather_url}" method="POST" />
</Response>"""

@app.route("/voice/gather", methods=["POST"])
def gather():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult")
    sid    = request.form.get("CallSid")

    if digits:
        send_tg(f"👆 المتصل اختار: {digits}\nCallSid: {sid}")
        if digits == "1":
            return """<?xml version="1.0" encoding="UTF-8"?><Response><Say language="ar-EG">هذه رسالة النادي. شكرًا لاتصالك.</Say></Response>"""
        if digits == "2":
            return """<?xml version="1.0" encoding="UTF-8"?><Response><Say language="ar-EG">هذه رسالة الشركة. شكرًا لاتصالك.</Say></Response>"""

    if speech:
        send_tg(f"🗣️ المتصل قال: {speech}\nCallSid: {sid}")

    return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="ar-EG">شكرًا. سيتم إنهاء المكالمة الآن.</Say>
  <Hangup/>
</Response>"""

@app.route("/voice/status", methods=["POST"])
def status():
    sid   = request.form.get("CallSid")
    st    = request.form.get("CallStatus")  # queued, ringing, in-progress, completed, busy, failed, no-answer...
    frm   = request.form.get("From")
    to    = request.form.get("To")
    send_tg(f"📊 حالة المكالمة: {st}\nFrom: {frm}\nTo: {to}\nCallSid: {sid}")
    return "ok"

# (اختياري) للمكالمات الواردة من رقم Twilio
@app.route("/voice/incoming", methods=["POST"])
def incoming():
    base = request.host_url
    gather_url = urljoin(base, "voice/gather")
    frm = request.form.get("From")
    sid = request.form.get("CallSid")
    send_tg(f"📞 اتصال وارد من: {frm}\nCallSid: {sid}")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="ar-EG">مرحبًا بك. اضغط واحد لرسالة النادي، أو اثنين لرسالة الشركة.</Say>
  <Gather input="dtmf speech" timeout="5" numDigits="1" action="{gather_url}" method="POST" />
</Response>"""

if __name__ == "__main__":
    import socket
    port = int(os.getenv("PORT", 5000))
    print(f"Running on http://0.0.0.0:{port} (host: {socket.gethostname()})")
    app.run(host="0.0.0.0", port=port)
