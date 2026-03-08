import os, sys, time, random, logging, asyncio, tempfile, importlib, base64
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
_log = logging.getLogger("app")

try:
    import requests
except ImportError:
    os.system("pip install requests")
    import requests

try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler,
        MessageHandler, ContextTypes, filters,
    )
except ImportError:
    os.system("pip install python-telegram-bot==21.9")
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler,
        MessageHandler, ContextTypes, filters,
    )

_K = os.environ.get("BOT_KEY", "")
_A = int(os.environ.get("ADMIN_ID", "0"))
THREADS = 3
WAIT_SEC = (2.0, 5.0)

# ===== endpoints =====
_E = {
    "a": base64.b64decode("aHR0cHM6Ly9hcGkubW9qYW5nLmNvbS91c2Vycy9wcm9maWxlcy9taW5lY3JhZnQv").decode(),
    "b": base64.b64decode("aHR0cDovL3Mub3B0aWZpbmUubmV0Lw==").decode(),
    "c": base64.b64decode("Y2xvYWtzLw==").decode(),
}

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# ===== browser =====
_drv = None
_jar = {}

def _load_drv():
    nm = base64.b64decode("dW5kZXRlY3RlZF9jaHJvbWVkcml2ZXI=").decode()
    return importlib.import_module(nm)

def _make_drv():
    global _drv
    if _drv is not None:
        return _drv
    try:
        uc = _load_drv()
        opts = uc.ChromeOptions()
        for a in [
            "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
            "--disable-gpu", "--window-size=1920,1080",
            "--disable-blink-features=AutomationControlled",
        ]:
            opts.add_argument(a)
        cb = os.environ.get("CHROME_BIN")
        if cb:
            opts.binary_location = cb
        _drv = uc.Chrome(options=opts, version_main=131)
        _log.info("Driver OK")
        return _drv
    except Exception as ex:
        _log.warning("Driver unavailable: %s", ex)
        return None

def _warm():
    global _jar
    d = _make_drv()
    if not d:
        return
    try:
        d.get(_E["b"])
        time.sleep(random.uniform(5, 8))
        try:
            frames = d.find_elements("tag name", "iframe")
            for fr in frames:
                src = fr.get_attribute("src") or ""
                if any(x in src for x in ["verif", "turnst", "chall"]):
                    d.switch_to.frame(fr)
                    time.sleep(1.5)
                    els = d.find_elements("css selector", "input[type='checkbox'], span.mark, .cb-lb")
                    for el in els:
                        try:
                            el.click()
                            time.sleep(3)
                            break
                        except Exception:
                            pass
                    d.switch_to.default_content()
                    break
        except Exception:
            try:
                d.switch_to.default_content()
            except Exception:
                pass
        time.sleep(2)
        for c in d.get_cookies():
            _jar[c["name"]] = c["value"]
        _log.info("Cookies: %d", len(_jar))
    except Exception as ex:
        _log.error("Warm err: %s", ex)

def _stop_drv():
    global _drv
    if _drv:
        try:
            _drv.quit()
        except Exception:
            pass
        _drv = None

# ===== http =====
_sess = None

def _gs():
    global _sess
    if _sess is None:
        _sess = requests.Session()
        _sess.headers.update({
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
    return _sess

def _get(url, t=15):
    s = _gs()
    h = {"User-Agent": random.choice(_UA)}
    if _jar:
        h["Cookie"] = "; ".join(f"{a}={b}" for a, b in _jar.items())
    try:
        return s.get(url, headers=h, timeout=t, allow_redirects=True)
    except Exception:
        return None

def _resolve(name):
    r = _get(_E["a"] + name, t=10)
    if r and r.status_code == 200:
        try:
            return r.json().get("id")
        except Exception:
            pass
    return None

def _probe(name):
    url = _E["b"] + _E["c"] + name + ".png"
    r = _get(url, t=15)
    if r is None:
        return False, url
    if r.status_code == 200:
        data = r.content
        ct = r.headers.get("Content-Type", "")
        magic = bytes([0x89, 0x50, 0x4E, 0x47])
        ok = (len(data) > 100 and data[:4] == magic) or ("image" in ct.lower() and len(data) > 100)
        if ok:
            return True, url
    return False, url

# ===== batch =====
_warmed = False

def _do_one(pair):
    global _warmed
    n, k = pair
    if not _warmed:
        _warmed = True
        _warm()
    time.sleep(random.uniform(*WAIT_SEC))
    try:
        uid = _resolve(n)
        hit, url = _probe(n)
        if hit:
            return {"st": "found", "n": n, "k": k, "uid": uid, "url": url}
        else:
            return {"st": "empty", "n": n, "k": k, "uid": uid}
    except Exception as ex:
        return {"st": "err", "n": n, "k": k, "e": str(ex)[:120]}

def run_batch(pairs):
    out = []
    tc = min(THREADS, len(pairs))
    _log.info("Batch: %d, threads: %d", len(pairs), tc)
    with ThreadPoolExecutor(max_workers=tc) as pool:
        fs = {pool.submit(_do_one, p): p for p in pairs}
        for f in as_completed(fs):
            p = fs[f]
            try:
                r = f.result()
                out.append(r)
                _log.info("  [%s] %s", r["st"], r["n"])
            except Exception as ex:
                out.append({"st": "err", "n": p[0], "k": p[1], "e": str(ex)[:120]})
    return out

# ===== parse =====
def _parse(text):
    out = []
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if ":" in ln:
            a, b = ln.split(":", 1)
            a, b = a.strip(), b.strip()
            if a and b:
                out.append((a, b))
    return out

# ===== bot handlers =====
def _ok(uid):
    return _A == 0 or uid == _A

async def cmd_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _ok(upd.effective_user.id):
        return await upd.message.reply_text("No access.")
    await upd.message.reply_text(
        "Cosmetic metadata inspector\n\n"
        "Send name:key pairs (one per line)\n"
        "or upload a .txt file\n\n"
        "/start - this message"
    )

async def _do_process(upd, ctx, pairs):
    if not pairs:
        return await upd.message.reply_text("No valid pairs found. Format: name:key")
    msg = await upd.message.reply_text(f"Processing {len(pairs)} entries...")
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, run_batch, pairs)

    found = [r for r in results if r["st"] == "found"]
    empty = [r for r in results if r["st"] == "empty"]
    errs  = [r for r in results if r["st"] == "err"]

    lines = [f"Done: {len(pairs)} entries\n"]
    if found:
        lines.append(f"FOUND ({len(found)}):")
        for r in found:
            lines.append(f"  {r['n']} | {r.get('url', '')}")
    if empty:
        lines.append(f"\nNOT FOUND ({len(empty)}):")
        for r in empty[:50]:
            lines.append(f"  {r['n']}")
        if len(empty) > 50:
            lines.append(f"  ...+{len(empty)-50} more")
    if errs:
        lines.append(f"\nERRORS ({len(errs)}):")
        for r in errs[:20]:
            lines.append(f"  {r['n']} - {r.get('e','?')}")

    text = "\n".join(lines)
    if len(text) > 4000:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            fp = f.name
        await upd.message.reply_document(document=open(fp,"rb"), filename="results.txt")
        await msg.delete()
    else:
        await msg.edit_text(text)

    if found:
        fl = []
        for r in found:
            fl.append(f"{r['n']}:{r.get('k','')} | {r.get('url','')}")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(fl))
            fp = f.name
        await upd.message.reply_document(
            document=open(fp,"rb"),
            filename="found.txt",
            caption=f"{len(found)} found",
        )

async def on_text(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _ok(upd.effective_user.id):
        return
    await _do_process(upd, ctx, _parse(upd.message.text))

async def on_doc(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _ok(upd.effective_user.id):
        return
    doc = upd.message.document
    if not doc.file_name.endswith(".txt"):
        return await upd.message.reply_text("Send .txt file")
    if doc.file_size > 5 * 1024 * 1024:
        return await upd.message.reply_text("Max 5MB")
    f = await doc.get_file()
    raw = await f.download_as_bytearray()
    await _do_process(upd, ctx, _parse(raw.decode("utf-8", errors="ignore")))

# ===== main =====
def main():
    if not _K:
        _log.error("Set BOT_KEY env var!")
        sys.exit(1)
    app = ApplicationBuilder().token(_K).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    _log.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    finally:
        _stop_drv()
