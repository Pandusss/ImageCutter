import asyncio
import logging
import os
import tempfile

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.exceptions import TelegramAPIError
from PIL import Image

from config import BOT_TOKEN
from image_processor import process_image, MIN_FRAGMENT_SIZE
from emoji_pack_manager import create_emoji_pack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_image_files: dict[int, str] = {}


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Отправь изображение — я превращу его в emoji‑pack.\n\n"
        "Поддерживаются photo и document."
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "1️⃣ Отправь изображение\n"
        "2️⃣ Выбери сетку\n"
        "3️⃣ Получи ссылку на emoji‑pack\n\n"
        "⚠️ Требуется Telegram Premium"
    )


@dp.message(F.photo | F.document)
async def handle_image(message: Message):
    status = await message.answer("⏳ Загружаю изображение...")

    try:
        file = message.photo[-1] if message.photo else message.document
        file_info = await bot.get_file(file.file_id)

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, "image")

        await bot.download_file(file_info.file_path, temp_path)

        image = Image.open(temp_path)
        width, height = image.size

        if width < MIN_FRAGMENT_SIZE or height < MIN_FRAGMENT_SIZE:
            raise ValueError("Изображение слишком маленькое")

        user_image_files[message.from_user.id] = temp_path

        keyboard = build_grid_keyboard(
            user_id=message.from_user.id,
            width=width,
            height=height,
        )

        await status.edit_text(
            f"📐 {width}×{height}\n\nВыбери размер сетки:",
            reply_markup=keyboard,
        )

    except Exception as e:
        await status.edit_text(f"❌ {e}")
        logger.exception("Image processing error")


@dp.callback_query(F.data.startswith("show_all_"))
async def show_all_sizes(callback: CallbackQuery):
    _, user_id = callback.data.split("_")
    user_id = int(user_id)

    if callback.from_user.id != user_id:
        await callback.answer("Не твое изображение", show_alert=True)
        return

    path = user_image_files.get(user_id)
    if not path or not os.path.exists(path):
        await callback.answer("Файл не найден", show_alert=True)
        return

    image = Image.open(path)
    width, height = image.size

    keyboard = build_grid_keyboard(
        user_id=user_id,
        width=width,
        height=height,
        mode="all",
    )

    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


def build_grid_keyboard(
    user_id: int,
    width: int,
    height: int,
    mode: str = "optimal",  # optimal | all
) -> InlineKeyboardMarkup:
    max_cols = min(width // MIN_FRAGMENT_SIZE, 15)
    max_rows = min(height // MIN_FRAGMENT_SIZE, 15)

    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for cols in range(2, max_cols + 1):
        for rows in range(2, max_rows + 1):
            total = cols * rows

            # Ограничения Telegram
            if not (12 <= total <= 48):
                continue

            # ✅ В режиме optimal показываем только "хорошие" варианты
            if mode == "optimal" and total not in {12, 16, 20, 24, 30, 36}:
                continue

            row.append(
                InlineKeyboardButton(
                    text=f"{cols}×{rows}",
                    callback_data=f"grid_{user_id}_{cols}_{rows}",
                )
            )

            if len(row) == 3:
                buttons.append(row)
                row = []

    if row:
        buttons.append(row)

    # ✅ Кнопка "Показать все размеры"
    if mode == "optimal":
        buttons.append(
            [
                InlineKeyboardButton(
                    text="➕ Показать все размеры",
                    callback_data=f"show_all_{user_id}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cleanup(path: str):
    try:
        os.remove(path)
        os.rmdir(os.path.dirname(path))
    except Exception:
        pass


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())