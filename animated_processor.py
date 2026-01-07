import os
import tempfile
import subprocess
from PIL import Image, ImageSequence

from config import EMOJI_SIZE


MAX_FRAMES = 60      # ~2 секунды при 30 FPS
FPS = 30


def process_animated(path: str, cols: int, rows: int) -> list[str]:
    """
    Обрабатывает GIF / animated WEBP.
    Возвращает список путей к .webm (по одному на emoji).
    """

    img = Image.open(path)

    frames = []
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        if i >= MAX_FRAMES:
            break
        frames.append(frame.convert("RGBA"))

    if not frames:
        raise ValueError("Анимация не содержит кадров")

    temp_dir = tempfile.mkdtemp()

    prepared_frames = [
        fit_to_grid(frame, cols, rows)
        for frame in frames
    ]

    fragments_per_frame = [
        split(frame, cols, rows)
        for frame in prepared_frames
    ]

    total_parts = cols * rows
    output_files: list[str] = []

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