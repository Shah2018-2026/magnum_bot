import os
import re
import base64
import logging
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT = """Ты проверяешь накладную на мясную продукцию.

На фото таблица с товарами. Для каждой строки:
1. Найди граммаж из названия товара (например 500ГР, 450ГР)
2. Найди количество упаковок (число в колонке количества)
3. Найди вес написанный вручную (число в последней колонке, например 3.00, 2.40)
4. Если написано "Нет" или "нет" — пропусти строку
5. Посчитай: граммаж/1000 × количество = ожидаемый вес
6. Сравни с написанным весом (допуск ±0.01)

Ответь СТРОГО в таком формате (ничего лишнего):

СТРОКА: [название товара коротко]
РАСЧЁТ: [кол-во] × [граммаж]г = [результат] кг
НАПИСАНО: [вес из накладной] кг
СТАТУС: OK или ОШИБКА

(повтори для каждой строки)

ИТОГО: [сумма всех написанных весов] кг
ИТОГ_СТАТУС: OK или ЕСТЬ_ОШИБКИ"""


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Проверяю накладную...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        file_bytes = await file.download_as_bytearray()
        image_b64 = base64.b64encode(file_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )

        result_text = response.content[0].text
        lines = result_text.strip().split("\n")

        output_lines = []
        has_error = False

        for line in lines:
            if line.startswith("СТАТУС:"):
                if "ОШИБКА" in line:
                    output_lines.append("СТАТУС: 🔴 ПРОВЕРЬ!")
                    has_error = True
                else:
                    output_lines.append("СТАТУС: ✅ OK")
            elif line.startswith("ИТОГ_СТАТУС:"):
                if "ОШИБКИ" in line:
                    output_lines.append("\n⚠️ ЕСТЬ РАСХОЖДЕНИЯ — ПРОВЕРЬ НАКЛАДНУЮ!")
                else:
                    output_lines.append("\n✅ ВСЁ СХОДИТСЯ")
            else:
                output_lines.append(line)

        await update.message.reply_text("\n".join(output_lines))

    except Exception as e:
        logging.error(f"Error: {e}")
        await update.message.reply_text("❌ Ошибка при обработке фото. Попробуй ещё раз.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 Пришли фото накладной — проверю вес по каждой позиции.")


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT, handle_text))

if __name__ == "__main__":
    app.run_polling()
