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
    fragments: List[str | Image.Image],
    user_id: int,
    user_username: str | None,
    progress_cb: ProgressCallback | None = None,
    is_animated: bool = False,
) -> str:
    """
    fragments:
      - STATIC  -> List[PIL.Image]
      - VIDEO   -> List[path_to_webm]

    is_animated:
      - False -> STATIC emoji (PNG)
      - True  -> VIDEO emoji (WEBM)
    """

    if not fragments:
        raise ValueError("Нет фрагментов")

    bot_username = (await bot.get_me()).username.lower()
    pack_name = f"p{user_id}_{int(datetime.now().timestamp())}_by_{bot_username}"
    title = f"emoji by @{user_username}" if user_username else f"emoji by {user_id}"

    temp_dir = tempfile.mkdtemp()
    files: list[str] = []

    try:
        # =================================================
        # PREPARE FILES
        # =================================================
        if is_animated:
            # fragments = paths to .webm
            for path in fragments:
                if not os.path.exists(path):
                    raise ValueError("WEBM файл не найден")
                files.append(path)
        else:
            # fragments = PIL images
            for i, img in enumerate(fragments):
                path = os.path.join(temp_dir, f"{i}.png")
                img.save(path, "PNG")
                files.append(path)

        total = len(files)

        sticker_format = (
            StickerFormat.VIDEO if is_animated else StickerFormat.STATIC
        )

        # =================================================
        # CREATE STICKER SET (FIRST EMOJI)
        # =================================================
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
                        format=sticker_format,
                    )
                ],
            )
        )

        if progress_cb:
            await progress_cb(1, total)

        # =================================================
        # ADD REST
        # =================================================
        for i, path in enumerate(files[1:], start=2):
            await bot(
                AddStickerToSet(
                    user_id=user_id,
                    name=pack_name,
                    sticker=InputSticker(
                        sticker=FSInputFile(path),
                        emoji_list=["▫️"],
                        format=sticker_format,
                    ),
                )
            )

            if progress_cb:
                await progress_cb(i, total)

        return f"https://t.me/addemoji/{pack_name}"

    finally:
        # =================================================
        # CLEANUP (only PNGs we created)
        # =================================================
        if not is_animated:
            for f in files:
                try:
                    os.remove(f)
                except Exception:
                    pass
            try:
                os.rmdir(temp_dir)
            except Exception:
                pass