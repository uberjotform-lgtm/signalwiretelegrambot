import os
import requests
from flask import Flask, request
from signalwire.rest import Client as SignalWireClient

app = Flask(__name__)

# --- الإعدادات ---
SIGNALWIRE_PROJECT = os.getenv("SIGNALWIRE_PROJECT")
SIGNALWIRE_TOKEN = os.getenv("SIGNALWIRE_TOKEN")
SIGNALWIRE_SPACE = os.getenv("SIGNALWIRE_SPACE")
SIGNALWIRE_NUMBER = os.getenv("SIGNALWIRE_NUMBER")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = SignalWireClient(SIGNALWIRE_PROJECT, SIGNALWIRE_TOKEN, signalwire_space=SIGNALWIRE_SPACE)
TG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# --- دالة إرسال رسالة إلى تيليجرام ---
def send_tg(text):
    requests.post(f"{TG_URL}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

# --- استقبال الأوامر من تيليجرام ---
@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.startswith("/call"):
            parts = text.split()
            if len(parts) < 2:
                send_tg("📞 اكتب /call + رقم الهاتف")
                return "ok"
            to_number = parts[1]
            call = client.calls.create(
                from_=SIGNALWIRE_NUMBER,
                to=to_number,
                url=f"https://{request.host}/voice/outbound-start",
                status_callback=f"https://{request.host}/voice/status",
                status_callback_event=["initiated", "ringing", "answered", "completed", "busy", "failed", "no-answer"]
            )
            send_tg(f"📤 بدء مكالمة مع {to_number}\nCallSid: {call.sid}")
    return "ok"

# --- استقبال المكالمة الصادرة ---
@app.route("/voice/outbound-start", methods=["POST"])
def outbound_start():
    return """<Response>
        <Say language="ar-EG">مرحبًا، شكرًا لاتصالك. اضغط واحد لرسالة النادي، أو اثنين لرسالة الشركة.</Say>
        <Gather input="dtmf speech" timeout="5" numDigits="1" action="/voice/gather" />
    </Response>"""

# --- استقبال DTMF / كلام ---
@app.route("/voice/gather", methods=["POST"])
def gather():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult")
    sid = request.form.get("CallSid")
    if digits:
        send_tg(f"👆 المتصل اختار: {digits}\nCallSid: {sid}")
    if speech:
        send_tg(f"🗣️ المتصل قال: {speech}\nCallSid: {sid}")
    return """<Response><Say language="ar-EG">شكرًا، سيتم تحويلك الآن.</Say></Response>"""

# --- حالة المكالمة ---
@app.route("/voice/status", methods=["POST"])
def status():
    sid = request.form.get("CallSid")
    status = request.form.get("CallStatus")
    send_tg(f"📊 حالة المكالمة: {status}\nCallSid: {sid}")
    return "ok"

@app.route("/")
def home():
    return "SignalWire + Telegram Bot is Running ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
