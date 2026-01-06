"""
Модуль для создания emoji pack через Telegram Bot API
Использует методы aiogram напрямую
"""
from typing import List
from PIL import Image
import tempfile
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from aiogram import Bot
from aiogram.types import FSInputFile, InputSticker
from aiogram.enums import StickerFormat, StickerType
from aiogram.methods import CreateNewStickerSet, AddStickerToSet


def create_progress_bar(current: int, total: int, bar_length: int = 10) -> str:
    """
    Создает текстовый прогресс-бар
    
    Args:
        current: Текущее значение
        total: Общее значение
        bar_length: Длина прогресс-бара в символах
    
    Returns:
        str: Строка с прогресс-баром
    """
    if total == 0:
        return "█" * bar_length
    
    filled = int(bar_length * current / total)
    empty = bar_length - filled
    percentage = int(100 * current / total)
    
    return "█" * filled + "░" * empty + f" {percentage}%"


async def create_emoji_pack(
    bot: Bot,
    fragments: List[Image.Image],
    user_id: int,
    user_username: str | None = None,
    progress_callback=None
) -> str:
    """
    Создает emoji pack из фрагментов изображения.
    
    В Telegram Bot API для создания emoji packs используется метод
    createNewStickerSet с типом "emoji".
    
    Args:
        bot: Экземпляр бота aiogram
        fragments: Список PIL Image объектов (фрагменты изображения)
        user_id: ID пользователя, который будет владельцем pack
        user_username: Username пользователя (опционально, если None - используется user_id)
    
    Returns:
        str: Ссылка на созданный emoji pack
    
    Raises:
        ValueError: Если список фрагментов пуст
        Exception: При ошибках Telegram API
    """
    if not fragments:
        raise ValueError("Список фрагментов пуст")
    
    # Генерируем уникальное имя для pack
    # Имя должно содержать только строчные буквы, цифры и подчеркивания
    # И должно заканчиваться на "_by_<bot_username>"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bot_username = (await bot.get_me()).username.lower()
    pack_name = f"pack_{timestamp}_{user_id}_by_{bot_username}"
    
    # Формируем название pack: "pack by @username" или "pack by user_12345"
    if user_username:
        # Убираем @ если есть
        username_clean = user_username.lstrip('@').lower()
        pack_title = f"pack by @{username_clean}"
    else:
        pack_title = f"pack by user_{user_id}"
    
    # Создаем временную директорию для хранения файлов
    temp_dir = tempfile.mkdtemp()
    temp_files = []
    
    try:
        # Сохраняем все фрагменты во временные файлы параллельно для ускорения
        temp_files = [None] * len(fragments)
        
        def save_fragment(fragment_data):
            """Сохраняет один фрагмент в файл"""
            i, fragment = fragment_data
            temp_path = os.path.join(temp_dir, f"emoji_{i}.png")
            fragment.save(temp_path, "PNG")
            return i, temp_path
        
        with ThreadPoolExecutor(max_workers=min(len(fragments), 8)) as executor:
            # Запускаем сохранение всех фрагментов параллельно
            future_to_index = {
                executor.submit(save_fragment, (i, fragment)): i 
                for i, fragment in enumerate(fragments)
            }
            
            # Собираем результаты в правильном порядке
            for future in as_completed(future_to_index):
                i, temp_path = future.result()
                temp_files[i] = temp_path
        
        # Создаем emoji pack через Bot API
        # В aiogram 3.x для создания sticker set используется метод create_new_sticker_set
        # Для emoji packs нужно указать sticker_type="emoji"
        
        # Создаем список стикеров для первого вызова
        first_sticker_file = FSInputFile(temp_files[0])
        
        # Создаем новый sticker set с первым стикером
        # Используем класс метода aiogram напрямую
        create_method = CreateNewStickerSet(
            user_id=user_id,
            name=pack_name,
            title=pack_title,
            stickers=[
                InputSticker(
                    sticker=first_sticker_file,
                    emoji_list=["🖼️"],  # Эмодзи-идентификатор
                    format=StickerFormat.STATIC  # Формат для статических изображений
                )
            ],
            sticker_type=StickerType.CUSTOM_EMOJI  # Тип для custom emoji packs
        )
        await bot(create_method)
        
        # Обновляем прогресс после создания pack
        if progress_callback:
            await progress_callback(1, len(fragments))
        
        # Добавляем остальные фрагменты как эмодзи
        for i, temp_file in enumerate(temp_files[1:], start=2):
            sticker_file = FSInputFile(temp_file)
            
            # Добавляем стикер в pack используя класс метода aiogram
            add_method = AddStickerToSet(
                user_id=user_id,
                name=pack_name,
                sticker=InputSticker(
                    sticker=sticker_file,
                    emoji_list=["🖼️"],
                    format=StickerFormat.STATIC  # Формат для статических изображений
                )
            )
            await bot(add_method)
            
            # Обновляем прогресс после каждого добавленного стикера
            if progress_callback:
                await progress_callback(i, len(fragments))
        
        # Формируем ссылку на pack
        # Формат ссылки: https://t.me/addstickers/PACK_NAME
        pack_link = f"https://t.me/addstickers/{pack_name}"
        
        return pack_link
        
    except Exception as e:
        # Передаем ошибку выше для обработки
        raise Exception(f"Ошибка при создании emoji pack: {str(e)}")
        
    finally:
        # Удаляем временные файлы
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        if os.path.exists(temp_dir):
            try:
                os.rmdir(temp_dir)
            except:
                pass
