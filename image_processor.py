"""
Модуль для обработки изображений: деление на части и масштабирование
"""
from PIL import Image
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import EMOJI_SIZE, MIN_FRAGMENT_SIZE


def calculate_grid(image_width: int, image_height: int) -> Tuple[int, int]:
    """
    Вычисляет оптимальную сетку (колонки x строки) для деления изображения.
    
    Цель: сделать части максимально квадратными, при этом каждая часть
    должна быть не меньше MIN_FRAGMENT_SIZE пикселей.
    
    Args:
        image_width: Ширина изображения
        image_height: Высота изображения
    
    Returns:
        Tuple[int, int]: (количество колонок, количество строк)
    """
    # Вычисляем максимальное количество частей по каждой оси
    max_cols = max(1, image_width // MIN_FRAGMENT_SIZE)
    max_rows = max(1, image_height // MIN_FRAGMENT_SIZE)
    
    # Если изображение слишком маленькое, возвращаем 1x1
    if max_cols == 0 or max_rows == 0:
        return (1, 1)
    
    # Вычисляем соотношение сторон изображения
    aspect_ratio = image_width / image_height
    
    # Пробуем разные варианты сетки, выбираем наиболее квадратные части
    best_cols = 1
    best_rows = 1
    best_ratio_diff = float('inf')
    
    for cols in range(1, max_cols + 1):
        for rows in range(1, max_rows + 1):
            # Размеры одной части
            part_width = image_width / cols
            part_height = image_height / rows
            
            # Проверяем минимальный размер
            if part_width < MIN_FRAGMENT_SIZE or part_height < MIN_FRAGMENT_SIZE:
                continue
            
            # Вычисляем соотношение сторон части
            part_ratio = part_width / part_height
            
            # Идеальное соотношение - 1:1 (квадрат)
            ratio_diff = abs(part_ratio - 1.0)
            
            # Также учитываем, насколько хорошо части покрывают изображение
            coverage = (cols * rows) / (max_cols * max_rows)
            
            # Комбинированная метрика: близость к квадрату + покрытие
            score = ratio_diff - coverage * 0.1
            
            if score < best_ratio_diff:
                best_ratio_diff = score
                best_cols = cols
                best_rows = rows
    
    return (best_cols, best_rows)


def split_image(
    image: Image.Image,
    cols: int = None,
    rows: int = None,
    prefitted: bool = False,
) -> List[Image.Image]:
    """
    Делит изображение на части согласно указанной сетке.
    
    Изображение НЕ сжимается и НЕ растягивается.
    Если изображение больше сетки - обрезается по центру.
    Если изображение меньше - центрируется с прозрачными краями.
    
    Args:
        image: PIL Image объект
        cols: Количество колонок (если None - вычисляется автоматически)
        rows: Количество строк (если None - вычисляется автоматически)
    
    Returns:
        List[Image.Image]: Список частей изображения
    """
    # Если размеры сетки не указаны, вычисляем оптимальную сетку
    if cols is None or rows is None:
        width, height = image.size
        cols, rows = calculate_grid(width, height)

    # Вычисляем целевой размер сетки (в пикселях)
    target_width = cols * EMOJI_SIZE
    target_height = rows * EMOJI_SIZE

    # Если изображение уже подогнано под сетку (prefitted=True), не центрируем повторно
    centered_image = image if prefitted else fit_image_to_grid(image, cols, rows)
    
    # Теперь делим уже центрированное изображение на части
    part_width = EMOJI_SIZE
    part_height = EMOJI_SIZE
    
    fragments = []
    
    for row in range(rows):
        for col in range(cols):
            # Вычисляем координаты обрезки
            left = col * part_width
            top = row * part_height
            right = left + part_width
            bottom = top + part_height
            
            # Обрезаем изображение
            fragment = centered_image.crop((left, top, right, bottom))
            fragments.append(fragment)
    
    return fragments


def scale_fragment(fragment: Image.Image) -> Image.Image:
    """
    Масштабирует фрагмент до размера эмодзи (EMOJI_SIZE x EMOJI_SIZE).
    
    Использует LANCZOS для качественного масштабирования.
    Сохраняет прозрачность, если она есть.
    
    Args:
        fragment: PIL Image объект фрагмента
    
    Returns:
        Image.Image: Масштабированный фрагмент
    """
    # Конвертируем в RGBA для сохранения прозрачности
    if fragment.mode != 'RGBA':
        fragment = fragment.convert('RGBA')
    
    # Масштабируем с высоким качеством
    scaled = fragment.resize((EMOJI_SIZE, EMOJI_SIZE), Image.Resampling.LANCZOS)
    
    return scaled


def fit_image_to_grid(image: Image.Image, grid_cols: int, grid_rows: int) -> Image.Image:
    """
    Пропорционально уменьшает изображение, чтобы оно полностью влезло в сетку,
    и размещает его по центру. Пустые области заполняются прозрачностью.
    
    Изображение НЕ растягивается, только пропорционально уменьшается (если нужно).
    
    Args:
        image: PIL Image объект
        grid_cols: Количество колонок в сетке
        grid_rows: Количество строк в сетке
    
    Returns:
        Image.Image: Изображение, пропорционально уменьшенное и размещенное по центру сетки
    """
    # Размер сетки в пикселях
    grid_width = grid_cols * EMOJI_SIZE
    grid_height = grid_rows * EMOJI_SIZE
    
    # Размеры исходного изображения
    img_width, img_height = image.size
    
    # Вычисляем коэффициент масштабирования, чтобы изображение полностью влезло в сетку
    # Используем меньший коэффициент для сохранения пропорций
    scale_x = grid_width / img_width
    scale_y = grid_height / img_height
    scale = min(scale_x, scale_y)  # Берем меньший, чтобы изображение полностью влезло
    
    # Новые размеры изображения после пропорционального уменьшения
    new_width = int(img_width * scale)
    new_height = int(img_height * scale)
    
    # Пропорционально уменьшаем изображение (если нужно)
    if scale < 1.0:
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    else:
        # Если изображение уже меньше сетки, используем оригинал
        resized_image = image
        new_width, new_height = img_width, img_height
    
    # Конвертируем в RGBA для поддержки прозрачности
    if resized_image.mode != 'RGBA':
        resized_image = resized_image.convert('RGBA')
    
    # Создаем прозрачный холст размером сетки
    canvas = Image.new('RGBA', (grid_width, grid_height), (0, 0, 0, 0))
    
    # Вычисляем позицию для размещения изображения по центру
    x_offset = (grid_width - new_width) // 2
    y_offset = (grid_height - new_height) // 2
    
    # Размещаем изображение по центру холста
    canvas.paste(resized_image, (x_offset, y_offset), resized_image)
    
    return canvas


def process_image(image_path: str, grid_cols: int = None, grid_rows: int = None) -> List[Image.Image]:
    """
    Основная функция обработки изображения.
    
    Загружает изображение, пропорционально уменьшает и размещает по центру сетки,
    затем делит на части. Пустые области заполняются прозрачностью.
    
    Args:
        image_path: Путь к файлу изображения
        grid_cols: Количество колонок сетки. Если None - вычисляется автоматически
        grid_rows: Количество строк сетки. Если None - вычисляется автоматически
    
    Returns:
        List[Image.Image]: Список обработанных фрагментов
    """
    # Загружаем изображение
    image = Image.open(image_path)
    
    # Конвертируем в RGBA для поддержки прозрачности
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Проверяем минимальный размер
    width, height = image.size
    if width < MIN_FRAGMENT_SIZE or height < MIN_FRAGMENT_SIZE:
        raise ValueError(
            f"Изображение слишком маленькое: {width}x{height}. "
            f"Минимальный размер: {MIN_FRAGMENT_SIZE}x{MIN_FRAGMENT_SIZE}"
        )
    
    # Обрабатываем изображение согласно указанной сетке
    if grid_cols is not None and grid_rows is not None:
        # Пропорционально уменьшаем и размещаем по центру сетки
        fitted_image = fit_image_to_grid(image, grid_cols, grid_rows)
        # Делим на части, используя уже подогнанное изображение
        fragments = split_image(fitted_image, cols=grid_cols, rows=grid_rows, prefitted=True)
    else:
        # Вычисляем оптимальную сетку автоматически
        fragments = split_image(image)
    
    # Масштабируем каждую часть параллельно для ускорения
    # Используем ThreadPoolExecutor, так как PIL частично освобождает GIL
    scaled_fragments = []
    with ThreadPoolExecutor(max_workers=min(len(fragments), 8)) as executor:
        # Запускаем масштабирование всех фрагментов параллельно
        future_to_fragment = {
            executor.submit(scale_fragment, fragment): i 
            for i, fragment in enumerate(fragments)
        }
        
        # Собираем результаты в правильном порядке
        results = [None] * len(fragments)
        for future in as_completed(future_to_fragment):
            index = future_to_fragment[future]
            results[index] = future.result()
        
        scaled_fragments = results
    
    return scaled_fragments
