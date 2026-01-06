import os
import tempfile
from datetime import datetime
from typing import List, Callable, Awaitable

from PIL import Image
from aiogram import Bot
from aiogram.types import FSInputFile, InputSticker
from aiogram.enums import StickerFormat, StickerType
from aiogram.methods import CreateNewStickerSet, AddStickerToSet


ProgressCallback = Callable[[int, int], Awaitable[None]]


async def create_emoji_pack(
    bot: Bot,
    fragments: List[Image.Image],
    user_id: int,
    user_username: str | None,
    progress_cb: ProgressCallback | None = None,
) -> str:
    if not fragments:
        raise ValueError("Нет фрагментов")

    bot_username = (await bot.get_me()).username.lower()
    pack_name = f"p{user_id}_{int(datetime.now().timestamp())}_by_{bot_username}"
    title = f"emoji by @{user_username}" if user_username else f"emoji by {user_id}"

    temp_dir = tempfile.mkdtemp()
    files: list[str] = []

    try:
        # сохраняем картинки
        for i, img in enumerate(fragments):
            path = os.path.join(temp_dir, f"{i}.png")
            img.save(path, "PNG")
            files.append(path)

        total = len(files)

        # создаём набор (1-й эмодзи)
        await bot(
            CreateNewStickerSet(
                user_id=user_id,
                name=pack_name,
                title=title,
                sticker_type=StickerType.CUSTOM_EMOJI,
                stickers=[
                    InputSticker(
                        sticker=FSInputFile(files[0]),
                        emoji_list=["▫️"],
                        format=StickerFormat.STATIC,
                    )
                ],
            )
        )

        if progress_cb:
            await progress_cb(1, total)

        # добавляем остальные
        for i, path in enumerate(files[1:], start=2):
            await bot(
                AddStickerToSet(
                    user_id=user_id,
                    name=pack_name,
                    sticker=InputSticker(
                        sticker=FSInputFile(path),
                        emoji_list=["▫️"],
                        format=StickerFormat.STATIC,
                    ),
                )
            )

            if progress_cb:
                await progress_cb(i, total)

        return f"https://t.me/addemoji/{pack_name}"

    finally:
        for f in files:
            try:
                os.remove(f)
            except Exception:
                pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass