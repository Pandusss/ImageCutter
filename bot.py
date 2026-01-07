import asyncio
import logging
import os
import re
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
# PROGRESS BAR
# =====================================================

def render_progress(current: int, total: int, width: int = 16) -> str:
    percent = int(current / total * 100)
    filled = int(width * percent / 100)
    bar = "█" * filled + "░" * (width - filled)
    return (
        "🧩 Создаю emoji‑pack\n"
        f"{bar} {percent}%\n"
        f"{current} / {total}"
    )


# =====================================================
# COMMANDS
# =====================================================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Отправь изображение или анимацию.\n\n"
        "Поддерживаются:\n"
        "🖼 PNG / JPG / WEBP — статичные emoji\n"
        "🎞 GIF / MP4 — анимированные emoji\n\n"
        "⚠️ Анимация: до 3 секунд, лучше 4–12 эмодзи."
    )


# =====================================================
# MEDIA HANDLER
# =====================================================

@dp.message(F.photo | F.document)
async def handle_media(message: Message):
    status = await message.answer("⏳ Загружаю файл…")

    try:
        if message.document:
            file = message.document
            filename = file.file_name
        else:
            file = message.photo[-1]
            filename = None

        file_info = await bot.get_file(file.file_id)

        # если Telegram не дал имя — генерируем сами
        if not filename:
            ext = os.path.splitext(file_info.file_path)[1] or ".bin"
            filename = f"file_{file.file_unique_id}{ext}"

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, filename)

        await bot.download_file(file_info.file_path, temp_path)

        ext = os.path.splitext(temp_path)[1].lower()

        is_animated = False

        # =================================================
        # STATIC IMAGES
        # =================================================
        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            img = Image.open(temp_path)
            width, height = img.size
            is_animated = getattr(img, "is_animated", False)

        # =================================================
        # TELEGRAM GIF (MP4)
        # =================================================
        elif ext in {".mp4", ".mov"}:
            is_animated = True
            # виртуальный размер ТОЛЬКО для сетки
            width = height = 1000

        else:
            raise ValueError("Неподдерживаемый формат файла")

        if width < MIN_FRAGMENT_SIZE or height < MIN_FRAGMENT_SIZE:
            raise ValueError("Файл слишком маленький")

        user_files[message.from_user.id] = {
            "path": temp_path,
            "animated": is_animated,
            "width": width,
            "height": height,
        }

        keyboard = build_grid_keyboard(
            user_id=message.from_user.id,
            width=width,
            height=height,
            mode="optimal",
        )

        label = "🎞 Анимация" if is_animated else "🖼 Изображение"

        await status.edit_text(
            f"{label}\n\nВыбери размер сетки:",
            reply_markup=keyboard,
        )

    except Exception as e:
        await status.edit_text(f"❌ {e}")
        logger.exception("Media error")


# =====================================================
# CALLBACKS
# =====================================================

@dp.callback_query(F.data.startswith("grid_"))
async def handle_grid(callback: CallbackQuery):
    _, user_id, cols, rows = callback.data.split("_")
    user_id, cols, rows = int(user_id), int(cols), int(rows)

    if callback.from_user.id != user_id:
        await callback.answer("Не твоё", show_alert=True)
        return

    data = user_files.get(user_id)
    if not data or not os.path.exists(data["path"]):
        await callback.answer("Файл не найден", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup()

    status = await callback.message.edit_text("🧩 Подготовка…")

    try:
        if data["animated"]:
            await status.edit_text("🎞 Обрабатываю анимацию…")
            fragments = process_animated(data["path"], cols, rows)
            is_animated = True
        else:
            fragments = process_image(data["path"], cols, rows)
            is_animated = False

        total = len(fragments)

        async def progress_cb(current: int, total: int):
            await status.edit_text(render_progress(current, total))

        pack_link = await create_emoji_pack(
            bot=bot,
            fragments=fragments,
            user_id=user_id,
            user_username=callback.from_user.username,
            progress_cb=progress_cb,
            is_animated=is_animated,
        )

        await status.edit_text(
            f"✅ Готово!\n\n"
            f"🧩 Эмодзи: {total}\n"
            f"🔗 {pack_link}"
        )

    except Exception as e:
        text = str(e)

        if "Too Many Requests" in text or "Flood control exceeded" in text:
            match = re.search(r"retry after (\d+)", text, re.IGNORECASE)
            seconds = int(match.group(1)) if match else 1800
            minutes = max(1, seconds // 60)

            await status.edit_text(
                "⏳ Telegram временно ограничил создание emoji‑packs.\n\n"
                f"Попробуй снова через ~{minutes} минут."
            )
        else:
            await status.edit_text(
                "❌ Не удалось создать emoji‑pack.\n\n"
                "Причины:\n"
                "• анимация слишком длинная\n"
                "• слишком много эмодзи\n"
                "• файл слишком тяжёлый\n\n"
                f"Ошибка: {e}"
            )
            logger.exception("Pack error")

    finally:
        cleanup(data["path"])
        user_files.pop(user_id, None)


@dp.callback_query(F.data.startswith("show_all_"))
async def show_all_sizes(callback: CallbackQuery):
    _, _, user_id = callback.data.split("_", 2)
    user_id = int(user_id)

    data = user_files.get(user_id)
    if not data:
        await callback.answer("Файл не найден", show_alert=True)
        return

    keyboard = build_grid_keyboard(
        user_id=user_id,
        width=data["width"],
        height=data["height"],
        mode="all",
    )

    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


# =====================================================
# KEYBOARD
# =====================================================

def build_grid_keyboard(
    user_id: int,
    width: int,
    height: int,
    mode: str = "optimal",
) -> InlineKeyboardMarkup:
    max_cols = min(width // MIN_FRAGMENT_SIZE, 15)
    max_rows = min(height // MIN_FRAGMENT_SIZE, 15)

    optimal_totals = {12, 16, 20, 24, 30, 36}

    all_btns = []
    opt_btns = []

    for c in range(2, max_cols + 1):
        for r in range(2, max_rows + 1):
            total = c * r
            if not (4 <= total <= 48):
                continue

            btn = InlineKeyboardButton(
                text=f"{c}×{r}",
                callback_data=f"grid_{user_id}_{c}_{r}",
            )
            all_btns.append(btn)
            if total in optimal_totals:
                opt_btns.append(btn)

    source = opt_btns if (mode == "optimal" and opt_btns) else all_btns

    keyboard, row = [], []
    for btn in source:
        row.append(btn)
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    if mode == "optimal" and opt_btns and len(all_btns) > len(opt_btns):
        keyboard.append(
            [InlineKeyboardButton(
                text="➕ Показать все размеры",
                callback_data=f"show_all_{user_id}",
            )]
        )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


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
# ENTRYPOINT
# =====================================================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())