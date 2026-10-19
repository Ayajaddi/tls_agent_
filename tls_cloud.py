"""
TLScontact watcher - نسخة Railway (headless).

محلياً (مرة وحدة):  python tls_cloud.py --login
   -> يحل المتصفح، تعمل login + reCAPTCHA، ثم Enter في الـ terminal.
   -> يطبع قيمة TLS_STATE_B64 (انسخها لـ Railway variables).

على Railway: python tls_cloud.py
"""
import argparse, base64, json, os, random, time
from datetime import datetime

import requests
from playwright.sync_api import sync_playwright

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE_B64 = os.environ.get("TLS_STATE_B64", "")
GROUP_ID = os.environ.get("GROUP_ID", "29061133")
VISA_TYPE = "Tourisme / court séjour"
MIN_S = int(os.environ.get("CHECK_MIN_SECONDS", "90"))
MAX_S = int(os.environ.get("CHECK_MAX_SECONDS", "180"))
REALERT = 300
STATE_PATH = os.environ.get("STATE_PATH", "/data/state.json")  # Railway Volume على /data

URL = f"https://visas-fr.tlscontact.com/workflow/appointment-booking/tnTUN2fr/{GROUP_ID}"
NO_SLOT = ["plus de créneaux de rendez-vous", "aucun créneau n’est disponible", "aucun créneau n'est disponible"]


def log(m): print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def tg(text, photo=None):
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        if photo:
            requests.post(f"{base}/sendPhoto", data={"chat_id": CHAT_ID, "caption": text},
                          files={"photo": ("slot.png", photo)}, timeout=20)
        else:
            requests.post(f"{base}/sendMessage", data={"chat_id": CHAT_ID, "text": text}, timeout=20)
    except Exception as e:
        log(f"telegram error: {e}")


def check(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    try: page.wait_for_load_state("networkidle", timeout=20000)
    except Exception: pass
    page.wait_for_timeout(3000)
    url, text = page.url.lower(), page.inner_text("body").lower()
    if "auth" in url or "connectez-vous à votre compte" in text: return "login"
    if "access denied" in text or "just a moment" in text or "blocked" in text: return "blocked"
    if any(m in text for m in NO_SLOT): return "none"
    if "appointment-booking" in url and "réservez votre rendez-vous" in text: return "slots"
    return "unknown"


def do_login():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto("https://visas-fr.tlscontact.com/fr-fr/travel-groups")
        input("اعمل login كامل، وكي تولي في صفحة travel-groups اضغط Enter هنا... ")
        state = ctx.storage_state()
        b.close()
    enc = base64.b64encode(json.dumps(state).encode()).decode()
    open("state_b64.txt", "w").write(enc)
    print("\nتحفظ في state_b64.txt. انسخ محتواه لـ Railway كـ TLS_STATE_B64.")


def watch():
    if not (BOT_TOKEN and CHAT_ID and STATE_B64):
        raise SystemExit("ناقصين variables: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / TLS_STATE_B64")
    if os.path.exists(STATE_PATH):
        state = json.load(open(STATE_PATH)); log("loaded saved state from volume")
    else:
        state = json.loads(base64.b64decode(STATE_B64))
    last_alert, warned, last = 0.0, None, None
    started = time.time()
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(storage_state=state, locale="fr-FR", viewport={"width": 1366, "height": 768})
        page = ctx.new_page()
        tg(f"✅ Watcher (Railway) بدا\n{VISA_TYPE} | group {GROUP_ID}")
        while True:
            try: s = check(page)
            except Exception as e:
                s = "unknown"; log(f"error: {e}")
            log(f"state = {s}")
            if s in ("slots", "none", "unknown"):
                try:
                    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
                    ctx.storage_state(path=STATE_PATH)   # يحفظ cookies المجددة
                except Exception as e:
                    log(f"save state error: {e}")
            if s == "slots":
                if time.time() - last_alert > REALERT:
                    tg(f"🚨 فما RDV متاح!\n{VISA_TYPE}\n{URL}", page.screenshot())
                    last_alert = time.time()
            elif s in ("login", "blocked"):
                if warned != s:
                    hrs = (time.time() - started) / 3600
                    msg = (f"⚠️ الـ session خرجت بعد {hrs:.1f} ساعة. اعمل login من جديد."
                           if s == "login" else "⛔ الموقع بلوكا الـ IP متاع Railway.")
                    tg(msg); warned = s
            else:
                warned = None
                if s == "none" and last == "slots": tg("ℹ️ الـ slots تسكروا.")
                if s == "none": last_alert = 0.0
            last = s
            time.sleep(random.uniform(MIN_S, MAX_S))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--login", action="store_true")
    do_login() if ap.parse_args().login else watch()
