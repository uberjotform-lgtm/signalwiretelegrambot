import os
import re
import requests
from flask import Flask, request
from signalwire.rest import Client as SignalWireClient

app = Flask(__name__)

# =========================
#   إعدادات من Environment
# =========================
SW_PROJECT   = os.getenv("SIGNALWIRE_PROJECT")
SW_TOKEN     = os.getenv("SIGNALWIRE_TOKEN")
SW_SPACE_URL = os.getenv("SIGNALWIRE_SPACE_URL")   # مثال: https://yourspace.signalwire.com
SW_FROM      = os.getenv("SIGNALWIRE_NUMBER")      # رقم SignalWire بصيغة دولية +1...
TG_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

TG_API = f"https://api.telegram.org/bot{TG_TOKEN}" if TG_TOKEN else ""

# تحويل الأرقام العربية إلى إنجليزية
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def send_tg(text: str):
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
    # مكتبة signalwire تقرأ SIGNALWIRE_SPACE_URL من البيئة تلقائيًا
    return SignalWireClient(SW_PROJECT, SW_TOKEN)

def to_e164(user_input: str, default_cc="+20"):
    """
    يطبع الرقم لصيغة E.164:
    - يشيل مسافات/شرطات/أقواس
    - يحوّل أرقام عربية لإنجليزية
    - يتعامل مع 00 / + / 0 المحلية (لمصر +20 كافتراضي)
    """
    if not user_input:
        return None
    s = user_input.strip().translate(AR_DIGITS)
    # شيل أي شيء غير + أو أرقام
    s = re.sub(r"[^\d+]", "", s)

    # لو بدأ بـ + وخلاص
    if s.startswith("+"):
        return s

    # لو بدأ بـ 00.. حوّل لأول + ثم باقي الأرقام
    if s.startswith("00"):
        return "+" + s[2:]

    # لو رقم محلي يبدأ بصفر (مثلاً 01xxxxxxxxx في مصر)
    if s.startswith("0"):
        return default_cc + s[1:]

    # لو أرقام فقط بدون + ولا 00 (نعتبره محلي لمصر)
    if re.fullmatch(r"\d+", s):
        # لو بيبدأ بـ1 ومكوَّن من 10 أو 11 رقم، نخمن مصر موبايل: ضيف +20
        return default_cc + s

    return None

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
        send_tg("البوت شغال ✅\nاكتب: /call 01xxxxxxxxx أو /call +2010xxxxxxx")
        return "ok"

    # /call <number>
    if text.lower().startswith("/call"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_tg("📞 اكتب بالشكل: /call 01xxxxxxxxx أو /call +2010xxxxxxx")
            return "ok"

        # طبّع الرقم لصيغة دولية
        raw = parts[1]
        to_number = to_e164(raw, default_cc="+20")
        if not to_number or not to_number.startswith("+"):
            send_tg(f"❌ الرقم غير صحيح: {raw}\nجرّب بالشكل: +2010xxxxxxx أو 01xxxxxxxxx")
            return "ok"

        base = request.host_url.rstrip('/')
        try:
            client = get_sw_client()
            call = client.calls.create(
                from_=SW_FROM,
                to=to_number,
                url=f"{base}/voice/outbound-start",
                status_callback=f"{base}/voice/status",
                method="POST"
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
    sid   = request.form.get("CallSid")
    st    = request.form.get("CallStatus")
    frm   = request.form.get("From")
    to    = request.form.get("To")
    send_tg(f"📊 حالة المكالمة: {st}\nFrom: {frm}\nTo: {to}\nCallSid: {sid}")
    return "ok"

# للتشغيل المحلي فقط
if __name__ == "__main__":
    import socket
    port = int(os.getenv("PORT", 5000))
    print(f"Running on http://0.0.0.0:{port} (host: {socket.gethostname()})")
    app.run(host="0.0.0.0", port=port)
