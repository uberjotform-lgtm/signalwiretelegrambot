import os
import requests
from flask import Flask, request
from signalwire.rest import Client as SignalWireClient

app = Flask(__name__)

# =========================
#   إعدادات من Environment
# =========================
SW_PROJECT   = os.getenv("SIGNALWIRE_PROJECT")
SW_TOKEN     = os.getenv("SIGNALWIRE_TOKEN")
SW_SPACE_URL = os.getenv("SIGNALWIRE_SPACE_URL")   # لازم تكون بالشكل: https://yourspace.signalwire.com
SW_FROM      = os.getenv("SIGNALWIRE_NUMBER")      # رقم SignalWire بصيغة دولية +1...
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

TG_API = f"https://api.telegram.org/bot{TG_TOKEN}" if TG_TOKEN else ""

def send_tg(text: str):
    """إرسال رسالة نصية إلى تيليجرام."""
    try:
        if TG_API and TG_CHAT_ID:
            requests.post(f"{TG_API}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": text})
    except Exception:
        pass

def missing_env():
    req = {
        "SIGNALWIRE_PROJECT": SW_PROJECT,
        "SIGNALWIRE_TOKEN": SW_TOKEN,
        "SIGNALWIRE_SPACE_URL": SW_SPACE_URL,
        "SIGNALWIRE_NUMBER": SW_FROM,
        "TELEGRAM_BOT_TOKEN": TG_TOKEN,
        "TELEGRAM_CHAT_ID": TG_CHAT_ID,
    }
    return [k for k, v in req.items() if not v]

def get_sw_client():
    # مكتبة signalwire (v2.x) بتقرأ SIGNALWIRE_SPACE_URL داخليًا — يكفي وجوده كمتغيّر بيئة
    return SignalWireClient(SW_PROJECT, SW_TOKEN)

@app.route("/")
def home():
    miss = missing_env()
    if miss:
        return f"Running, but missing env vars: {', '.join(miss)}", 500
    return "SignalWire + Telegram Bot is Running ✅", 200

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
        send_tg("البوت شغال ✅\nاكتب: /call +2010xxxxxxx")
        return "ok"

    # /call +2010xxxxxxx
    if text.lower().startswith("/call"):
        parts = text.split()
        if len(parts) < 2:
            send_tg("📞 اكتب بالشكل: /call +2010xxxxxxx")
            return "ok"

        to_number = parts[1]
        base = request.host_url.rstrip('/')

        try:
            client = get_sw_client()
            call = client.calls.create(
                from_=SW_FROM,
                to=to_number,
                url=f"{base}/voice/outbound-start",
                status_callback=f"{base}/voice/status",
                method="POST"  # مهم: POST
            )
            send_tg(f"📤 بدء مكالمة مع {to_number}\nCallSid: {call.sid}")
        except Exception as e:
            send_tg(f"❌ فشل بدء المكالمة: {e}")
        return "ok"

    return "ok"

# =========================
#   تدفق المكالمة (cXML/TwiML)
# =========================
@app.route("/voice/outbound-start", methods=["POST"])
def outbound_start():
    base = request.host_url.rstrip('/')
    # نستخدم URL مطلق في action لضمان وصول POST من خلف البروكسي
    return f"""<Response>
  <Say language="ar-EG">مرحبًا، شكرًا لاتصالك. اضغط واحد لرسالة النادي، أو اثنين لرسالة الشركة.</Say>
  <Gather input="dtmf speech" timeout="5" numDigits="1" action="{base}/voice/gather" method="POST" />
</Response>"""

@app.route("/voice/gather", methods=["POST"])
def gather():
    digits = request.form.get("Digits")
    speech = request.form.get("SpeechResult")
    sid    = request.form.get("CallSid")

    if digits:
        send_tg(f"👆 المتصل اختار: {digits}\nCallSid: {sid}")
        if digits == "1":
            return """<Response><Say language="ar-EG">هذه رسالة النادي. شكرًا لاتصالك.</Say></Response>"""
        elif digits == "2":
            return """<Response><Say language="ar-EG">هذه رسالة الشركة. شكرًا لاتصالك.</Say></Response>"""

    if speech:
        send_tg(f"🗣️ المتصل قال: {speech}\nCallSid: {sid}")

    return """<Response>
  <Say language="ar-EG">شكرًا. سيتم إنهاء المكالمة الآن.</Say>
  <Hangup/>
</Response>"""

@app.route("/voice/status", methods=["POST"])
def status():
    # SignalWire سترسل حالات متعددة؛ عند النهاية CallStatus قد يكون completed/busy/failed/no-answer...
    sid   = request.form.get("CallSid")
    st    = request.form.get("CallStatus")
    frm   = request.form.get("From")
    to    = request.form.get("To")
    send_tg(f"📊 حالة المكالمة: {st}\nFrom: {frm}\nTo: {to}\nCallSid: {sid}")
    return "ok"

# تشغيل محليًا فقط (Render يستخدم gunicorn من Procfile)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
