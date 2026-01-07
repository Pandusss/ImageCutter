import os
import tempfile
import subprocess
from PIL import Image

from config import EMOJI_SIZE


MAX_FRAMES = 60      # ~2 секунды при 30 FPS
FPS = 30


def process_animated(path: str, cols: int, rows: int) -> list[str]:
    """
    Поддерживает:
      - GIF
      - animated WEBP
      - MP4 (Telegram GIF)

    Возвращает список путей к .webm (по одному на emoji).
    """

    temp_dir = tempfile.mkdtemp()

    # =================================================
    # 1. EXTRACT FRAMES (ffmpeg handles everything)
    # =================================================
    frames_dir = os.path.join(temp_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    extract_frames(path, frames_dir)

    frame_files = sorted(
        f for f in os.listdir(frames_dir) if f.endswith(".png")
    )

    if not frame_files:
        raise ValueError("Не удалось извлечь кадры из анимации")

    # ограничиваем длительность
    frame_files = frame_files[:MAX_FRAMES]

    frames = [
        Image.open(os.path.join(frames_dir, f)).convert("RGBA")
        for f in frame_files
    ]

    # =================================================
    # 2. FIT TO GRID
    # =================================================
    prepared_frames = [
        fit_to_grid(frame, cols, rows)
        for frame in frames
    ]

    # =================================================
    # 3. SPLIT EACH FRAME
    # =================================================
    fragments_per_frame = [
        split(frame, cols, rows)
        for frame in prepared_frames
    ]

    total_parts = cols * rows
    output_files: list[str] = []

    # =================================================
    # 4. BUILD WEBM PER EMOJI
    # =================================================
    for i in range(total_parts):
        part_dir = os.path.join(temp_dir, f"part_{i}")
        os.makedirs(part_dir, exist_ok=True)

        for f_idx, fragments in enumerate(fragments_per_frame):
            fragments[i].save(
                os.path.join(part_dir, f"{f_idx:03}.png")
            )

        out_path = os.path.join(temp_dir, f"{i}.webm")
        encode_webm(part_dir, out_path)
        output_files.append(out_path)

    return output_files


# =====================================================
# HELPERS
# =====================================================

def extract_frames(src: str, out_dir: str):
    """
    Извлекает PNG‑кадры из любого видео/гифки
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", src,
        "-vf", f"fps={FPS}",
        os.path.join(out_dir, "%03d.png"),
    ]
    subprocess.run(cmd, check=True)


def fit_to_grid(image: Image.Image, cols: int, rows: int) -> Image.Image:
    gw, gh = cols * EMOJI_SIZE, rows * EMOJI_SIZE
    iw, ih = image.size

    scale = min(gw / iw, gh / ih)
    nw, nh = int(iw * scale), int(ih * scale)

    image = image.resize((nw, nh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    canvas.paste(image, ((gw - nw) // 2, (gh - nh) // 2), image)
    return canvas


def split(image: Image.Image, cols: int, rows: int):
    parts = []
    for y in range(rows):
        for x in range(cols):
            left = x * EMOJI_SIZE
            top = y * EMOJI_SIZE
            parts.append(
                image.crop((left, top, left + EMOJI_SIZE, top + EMOJI_SIZE))
            )
    return parts


def encode_webm(frame_dir: str, out_path: str):
    """
    Кодирует WEBM под требования Telegram emoji
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frame_dir, "%03d.png"),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-b:v", "0",
        "-crf", "40",
        "-an",
        out_path,
    ]
    subprocess.run(cmd, check=True)