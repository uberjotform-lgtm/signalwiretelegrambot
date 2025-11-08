import os
import requests
from flask import Flask, request
from signalwire.rest import Client as SignalWireClient

app = Flask(__name__)

# ----- متغيّرات البيئة (تتضاف من Render فقط) -----
SIGNALWIRE_PROJECT = os.getenv("SIGNALWIRE_PROJECT")
SIGNALWIRE_TOKEN   = os.getenv("SIGNALWIRE_TOKEN")
# مهم: المكتبة تتوقع SIGNALWIRE_SPACE_URL بالـ https من Environment
# مثال القيمة على Render: https://uberdrink1.signalwire.com

SIGNALWIRE_NUMBER  = os.getenv("SIGNALWIRE_NUMBER")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# عميل سيجنالواير (من غير signalwire_space في المُنشئ)
client = SignalWireClient(SIGNALWIRE_PROJECT, SIGNALWIRE_TOKEN)
TG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send_tg(text):
    if TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN:
        try:
            requests.post(f"{TG_URL}/sendMessage",
                          data={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        except Exception:
            pass

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}
    msg = data.get("message") or {}
    text = (msg.get("text") or "").strip()

    if text.startswith("/call"):
        parts = text.split()
        if len(parts) < 2:
            send_tg("📞 اكتب: /call +2010xxxxxxx")
            return "ok"
        to_number = parts[1]
        # استخدم رابط كامل للـ URLs
        base = request.host_url.rstrip('/')
        call = client.calls.create(
            from_=SIGNALWIRE_NUMBER,
            to=to_number,
            url=f"{base}/voice/outbound-start",
            status_callback=f"{base}/voice/status",
            status_callback_event=[
                "initiated", "ringing", "answered",
                "completed", "busy", "failed", "no-answer"
            ]
        )
        send_tg(f"📤 بدء مكالمة مع {to_number}\nCallSid: {call.sid}")
    return "ok"

@app.route("/voice/outbound-start", methods=["POST"])
def outbound_start():
    base = request.host_url.rstrip('/')
    return f"""<Response>
        <Say language="ar-EG">مرحبًا، شكرًا لاتصالك. اضغط 1 لرسالة النادي، أو 2 لرسالة الشركة.</Say>
        <Gather input="dtmf speech" timeout="5" numDigits="1" action="{base}/voice/gather" />
    </Response>"""

@app.route("/voice/gather", methods=["POST"])
def gather():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult")
    sid = request.form.get("CallSid")
    if digits:
        send_tg(f"👆 المتصل اختار: {digits}\nCallSid: {sid}")
    if speech:
        send_tg(f"🗣️ المتصل قال: {speech}\nCallSid: {sid}")
    return """<Response>
        <Say language="ar-EG">شكرًا، سيتم تحويلك الآن.</Say>
    </Response>"""

@app.route("/voice/status", methods=["POST"])
def status():
    sid = request.form.get("CallSid")
    st  = request.form.get("CallStatus")
    send_tg(f"📊 حالة المكالمة: {st}\nCallSid: {sid}")
    return "ok"

@app.route("/")
def home():
    return "SignalWire + Telegram Bot is Running ✅"
