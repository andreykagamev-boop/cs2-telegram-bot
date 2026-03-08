import os
import sys
import asyncio
import tempfile
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("app")

try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler,
        MessageHandler, ContextTypes, filters,
    )
except ImportError:
    log.error("pip install python-telegram-bot==21.9")
    sys.exit(1)

from worker import run_batch, stop_drv

_K = os.environ.get("BOT_KEY", "")
_A = int(os.environ.get("ADMIN_ID", "0"))


def allowed(uid):
    return _A == 0 or uid == _A


def parse(text):
    out = []
    for ln in text.strip().splitlines():
        ln = ln.strip()
        if ":" in ln:
            a, b = ln.split(":", 1)
            a, b = a.strip(), b.strip()
            if a and b:
                out.append((a, b))
    return out


async def cmd_start(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(upd.effective_user.id):
        return await upd.message.reply_text("No access.")
    await upd.message.reply_text(
        "Skin metadata tool\n\n"
        "Send name:value pairs (one per line)\n"
        "or upload a .txt file\n\n"
        "/start - this message"
    )


async def process(upd: Update, ctx: ContextTypes.DEFAULT_TYPE, pairs):
    if not pairs:
        return await upd.message.reply_text("No valid pairs. Use  name:value  format.")

    msg = await upd.message.reply_text(f"Working on {len(pairs)} entries...")

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
            lines.append(f"  ...+{len(empty) - 50} more")

    if errs:
        lines.append(f"\nERRORS ({len(errs)}):")
        for r in errs[:20]:
            lines.append(f"  {r['n']} - {r.get('e', '?')}")

    text = "\n".join(lines)

    if len(text) > 4000:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(text)
            fp = f.name
        await upd.message.reply_document(document=open(fp, "rb"), filename="results.txt")
        await msg.delete()
    else:
        await msg.edit_text(text)

    if found:
        fl = []
        for r in found:
            fl.append(f"{r['n']}:{r.get('k', '')} | {r.get('url', '')}")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(fl))
            fp = f.name
        await upd.message.reply_document(
            document=open(fp, "rb"),
            filename="found.txt",
            caption=f"{len(found)} found",
        )


async def on_text(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(upd.effective_user.id):
        return
    await process(upd, ctx, parse(upd.message.text))


async def on_doc(upd: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not allowed(upd.effective_user.id):
        return
    doc = upd.message.document
    if not doc.file_name.endswith(".txt"):
        return await upd.message.reply_text("Send .txt file")
    if doc.file_size > 5 * 1024 * 1024:
        return await upd.message.reply_text("Max 5MB")
    f = await doc.get_file()
    raw = await f.download_as_bytearray()
    await process(upd, ctx, parse(raw.decode("utf-8", errors="ignore")))


def main():
    if not _K:
        log.error("Set BOT_KEY env!")
        sys.exit(1)
    app = ApplicationBuilder().token(_K).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.Document.ALL, on_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Polling started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        stop_drv()
