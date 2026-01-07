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
from PIL import Image

from config import BOT_TOKEN
from image_processor import process_image, MIN_FRAGMENT_SIZE
from animated_processor import process_animated
from emoji_pack_manager import create_emoji_pack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_files: dict[int, dict] = {}


# =====================================================
# START
# =====================================================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Отправь изображение или анимацию.\n"
        "PNG / JPG / WEBP / GIF / MP4"
    )


# =====================================================
# MEDIA
# =====================================================

@dp.message(F.photo | F.document)
async def handle_media(message: Message):
    msg = await message.answer("⏳ Загружаю файл…")

    try:
        if message.document:
            file = message.document
            filename = file.file_name
        else:
            file = message.photo[-1]
            filename = f"photo_{file.file_unique_id}.png"

        file_info = await bot.get_file(file.file_id)

        temp_dir = tempfile.mkdtemp()
        path = os.path.join(temp_dir, filename)

        await bot.download_file(file_info.file_path, path)

        ext = os.path.splitext(path)[1].lower()
        animated = False

        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            img = Image.open(path)
            width, height = img.size
            animated = getattr(img, "is_animated", False)

        elif ext in {".mp4", ".mov"}:
            animated = True
            width = height = 1000  # фиктивный размер

        else:
            raise ValueError("Неподдерживаемый формат")

        user_files[message.from_user.id] = {
            "path": path,
            "animated": animated,
            "width": width,
            "height": height,
        }

        keyboard = build_keyboard(
            message.from_user.id,
            width,
            height,
            show_all=False,
        )

        await msg.edit_text(
            "🎞 Анимация" if animated else "🖼 Изображение",
            reply_markup=keyboard,
        )

    except Exception as e:
        await msg.edit_text(f"❌ {e}")
        logger.exception("media error")


# =====================================================
# CALLBACKS
# =====================================================

@dp.callback_query(F.data.startswith("grid_"))
async def on_grid(callback: CallbackQuery):
    _, user_id, c, r = callback.data.split("_")
    user_id, c, r = int(user_id), int(c), int(r)

    if callback.from_user.id != user_id:
        await callback.answer("Не твоё", show_alert=True)
        return

    data = user_files.get(user_id)
    if not data:
        await callback.answer("Файл не найден", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup()

    status = await callback.message.edit_text("🧩 Генерирую…")

    try:
        if data["animated"]:
            parts = process_animated(data["path"], c, r)
            animated = True
        else:
            parts = process_image(data["path"], c, r)
            animated = False

        async def progress(i, t):
            await status.edit_text(f"{i}/{t}")

        link = await create_emoji_pack(
            bot=bot,
            fragments=parts,
            user_id=user_id,
            user_username=callback.from_user.username,
            progress_cb=progress,
            is_animated=animated,
        )

        await status.edit_text(f"✅ Готово\n{link}")

    except Exception as e:
        await status.edit_text(f"❌ {e}")
        logger.exception("pack error")

    finally:
        cleanup(data["path"])
        user_files.pop(user_id, None)


@dp.callback_query(F.data.startswith("all_"))
async def show_all(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    data = user_files.get(user_id)

    if not data:
        await callback.answer()
        return

    keyboard = build_keyboard(
        user_id,
        data["width"],
        data["height"],
        show_all=True,
    )

    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# =====================================================
# KEYBOARD
# =====================================================

def build_keyboard(user_id: int, width: int, height: int, show_all: bool):
    max_c = min(width // MIN_FRAGMENT_SIZE, 15)
    max_r = min(height // MIN_FRAGMENT_SIZE, 15)

    buttons = []

    for c in range(2, max_c + 1):
        for r in range(2, max_r + 1):
            total = c * r
            if not show_all and total not in {4, 6, 9, 12, 16}:
                continue
            if 4 <= total <= 48:
                buttons.append(
                    InlineKeyboardButton(
                        text=f"{c}×{r}",
                        callback_data=f"grid_{user_id}_{c}_{r}",
                    )
                )

    rows, row = [], []
    for b in buttons:
        row.append(b)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    if not show_all:
        rows.append([
            InlineKeyboardButton(
                text="➕ Показать все размеры",
                callback_data=f"all_{user_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# =====================================================
# UTILS
# =====================================================

def cleanup(path: str):
    try:
        os.remove(path)
        os.rmdir(os.path.dirname(path))
    except Exception:
        pass


# =====================================================
# RUN
# =====================================================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())