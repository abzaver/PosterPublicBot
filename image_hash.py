import asyncio
import tempfile
from pathlib import Path

from PIL import Image
import imagehash
import ffmpeg

ANIMATION_TILE_SIZE = "3x2"
ANIMATION_FRAMES = 6


async def phash_from_file(path: str | Path) -> str:
    return await asyncio.to_thread(_phash_sync, str(path))


async def phash_from_bytes(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as f:
        f.write(data)
        tmp_path = f.name
    try:
        return await asyncio.to_thread(_phash_sync, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def phash_from_animation(path: str | Path) -> str:
    return await asyncio.to_thread(_animation_phash_sync, str(path))


def _phash_sync(path: str) -> str:
    return str(imagehash.phash(Image.open(path)))


def _animation_phash_sync(in_path: str) -> str:
    probe = ffmpeg.probe(in_path)
    frames = 0
    for stream in probe["streams"]:
        if stream["codec_type"] == "video":
            frames = int(stream["nb_frames"]) // ANIMATION_FRAMES
            break

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
        tile_path = f.name

    try:
        frame_select = "+".join(
            f"eq(n,{frames * i})" for i in range(ANIMATION_FRAMES)
        )
        (
            ffmpeg
            .input(in_path)
            .filter("scale", 640, -1)
            .filter("select", frame_select)
            .filter("tile", ANIMATION_TILE_SIZE)
            .output(tile_path, vframes=1, vsync=0)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        return str(imagehash.phash(Image.open(tile_path)))
    finally:
        Path(tile_path).unlink(missing_ok=True)
