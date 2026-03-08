import os
import sys
import asyncio
import tempfile
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("bot")

try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        ContextTypes,
        filters,
    )
except ImportError:
    log.error("pip install python-telegram-bot==21.9")
    sys.exit(1)

from worker import process_batch, shutdown_browser

BOT_KEY = os.environ.get("BOT_KEY", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))


def is_allowed(uid: int) -> bool:
    return ADMIN_ID == 0 or uid == ADMIN_ID


def parse_lines(text: str):
    result = []
    for line in text.strip().splitlines():
        line = line.strip()
        if ":" in line:
            parts = line.split(":", 1)
            a, b = parts[0].strip(), parts[1].strip()
            if a and b:
                result.append((a, b))
    return result


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text("Access denied.")
        return
    await update.message.reply_text(
        "OptiFine Cape Checker\n\n"
        "Send nick:password (one per line)\n"
        "or upload a .txt file\n\n"
        "/start - help\n"
        "/stats - statistics"
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    s = ctx.bot_data.get("stats", {"total": 0, "cape": 0, "no": 0, "err": 0})
    await update.message.reply_text(
        f"Stats\n\n"
        f"Total: {s['total']}\n"
        f"With cape: {s['cape']}\n"
        f"No cape: {s['no']}\n"
        f"Errors: {s['err']}"
    )


async def do_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE, pairs):
    if not pairs:
        await update.message.reply_text("No valid entries. Format: nick:password")
        return

    msg = await update.message.reply_text(
        f"Processing {len(pairs)} entries... Please wait."
    )

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, process_batch, pairs)

    s = ctx.bot_data.get("stats", {"total": 0, "cape": 0, "no": 0, "err": 0})

    with_cape = []
    without_cape = []
    errors = []

    for r in results:
        s["total"] += 1
        if r["status"] == "has_cape":
            s["cape"] += 1
            with_cape.append(r)
        elif r["status"] == "no_cape":
            s["no"] += 1
            without_cape.append(r)
        else:
            s["err"] += 1
            errors.append(r)

    ctx.bot_data["stats"] = s

    lines = [f"Done! Checked {len(pairs)} entries.\n"]

    if with_cape:
        lines.append(f"WITH CAPE ({len(with_cape)}):")
        for r in with_cape:
            lines.append(f"  {r['nick']} - {r.get('cape_url', 'yes')}")

    if without_cape:
        lines.append(f"\nNO CAPE ({len(without_cape)}):")
        for r in without_cape[:50]:
            lines.append(f"  {r['nick']}")
        if len(without_cape) > 50:
            lines.append(f"  ...and {len(without_cape) - 50} more")

    if errors:
        lines.append(f"\nERRORS ({len(errors)}):")
        for r in errors[:20]:
            lines.append(f"  {r['nick']} - {r.get('error', '?')}")

    text = "\n".join(lines)

    if len(text) > 4000:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            fpath = f.name
        await update.message.reply_document(
            document=open(fpath, "rb"), filename="results.txt"
        )
        await msg.delete()
    else:
        await msg.edit_text(text)

    if with_cape:
        cape_lines = []
        for r in with_cape:
            cape_lines.append(f"{r['nick']}:{r.get('pwd', '')} | {r.get('cape_url', '')}")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("\n".join(cape_lines))
            fpath = f.name
        await update.message.reply_document(
            document=open(fpath, "rb"),
            filename="with_cape.txt",
            caption=f"{len(with_cape)} accounts with cape",
        )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    pairs = parse_lines(update.message.text)
    await do_check(update, ctx, pairs)


async def on_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("Send a .txt file.")
        return
    if doc.file_size > 5 * 1024 * 1024:
        await update.message.reply_text("File too large (max 5MB).")
        return
    tg_file = await doc.get_file()
    data = await tg_file.download_as_bytearray()
    text = data.decode("utf-8", errors="ignore")
    pairs = parse_lines(text)
    await do_check(update, ctx, pairs)


def main():
    if not BOT_KEY:
        log.error("Set BOT_KEY env variable!")
        sys.exit(1)

    log.info("Starting bot...")
    app = ApplicationBuilder().token(BOT_KEY).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.Document.ALL, on_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    log.info("Bot running. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown_browser()