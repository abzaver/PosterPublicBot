"""
CLI и библиотечный модуль для импорта истории канала из выгрузки Telegram Desktop.

Использование CLI:
    python importer.py --json result.json --workspace-id 1
    python importer.py --zip export.zip --workspace-id 1
"""

import argparse
import asyncio
import json
import os
import zipfile
import tempfile
import logging
from pathlib import Path

from PIL import Image
import imagehash

import storage
from image_hash import _animation_phash_sync

logger = logging.getLogger(__name__)


def _telegram_chat_id(raw_id: int, chat_type: str) -> int:
    if chat_type in ("public_supergroup", "private_supergroup",
                     "public_channel", "private_channel"):
        return -1000000000000 - int(raw_id)
    return int(raw_id)


def _parse_json(json_path: str) -> tuple[int, list[tuple]]:
    """Парсит result.json, возвращает (chat_id, список (chat_id, phash, msg_id, timestamp))."""
    base_dir = os.path.normpath(os.path.dirname(json_path))

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    raw_id = data.get("id", 0)
    chat_type = data.get("type", "")
    chat_id = _telegram_chat_id(raw_id, chat_type)

    media_msgs = [
        m for m in data.get("messages", [])
        if "photo" in m or (m.get("media_type") in ("animation", "video_file") and "file" in m)
    ]
    total = len(media_msgs)

    rows = []
    skipped = 0
    for i, msg in enumerate(media_msgs, 1):
        if "photo" in msg:
            img_rel = msg["photo"]
            is_video = False
        else:
            img_rel = msg["file"]
            is_video = True

        print(f"\r[{i}/{total}] {os.path.basename(img_rel)[:50]:<50}", end="", flush=True)

        img_path = os.path.join(base_dir, img_rel)
        if not os.path.exists(img_path):
            skipped += 1
            continue
        try:
            if is_video:
                phash = _animation_phash_sync(img_path)
            else:
                phash = str(imagehash.phash(Image.open(img_path)))
        except Exception as e:
            logger.warning("\nНе удалось хэшировать %s: %s", img_path, e)
            skipped += 1
            continue

        msg_id = msg.get("id", 0)
        timestamp = int(msg.get("date_unixtime", 0))
        rows.append((chat_id, phash, msg_id, timestamp))

    if total:
        print()  # перенос строки после прогресса

    if skipped:
        logger.info("Пропущено файлов: %d", skipped)

    return chat_id, rows


async def import_from_json(json_path: str, workspace_id: int) -> dict:
    """Импортирует хэши из result.json в БД. Возвращает статистику."""
    chat_id, rows = await asyncio.to_thread(_parse_json, json_path)

    added = 0
    skipped = 0
    for chat_id_r, phash, msg_id, timestamp in rows:
        if await storage.image_exists(workspace_id, chat_id_r, msg_id):
            skipped += 1
            continue
        await storage.add_image(
            workspace_id=workspace_id,
            chat_id=chat_id_r,
            phash=phash,
            msg_id=msg_id,
        )
        added += 1

    return {"added": added, "skipped": skipped, "chat_id": chat_id}


async def import_from_zip(zip_path: str, workspace_id: int) -> dict:
    """Распаковывает ZIP-архив выгрузки Telegram и импортирует хэши."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        await asyncio.to_thread(_extract_zip, zip_path, tmp_dir)

        # Ищем result.json в корне или в подпапке
        json_path = None
        for candidate in [
            os.path.join(tmp_dir, "result.json"),
            *Path(tmp_dir).rglob("result.json"),
        ]:
            if os.path.exists(str(candidate)):
                json_path = str(candidate)
                break

        if not json_path:
            raise FileNotFoundError("result.json не найден в архиве")

        return await import_from_json(json_path, workspace_id)


def _extract_zip(zip_path: str, target_dir: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(target_dir)


async def _cli_main() -> None:
    parser = argparse.ArgumentParser(description="Импорт истории Telegram в БД бота")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", metavar="PATH", help="Путь к result.json")
    group.add_argument("--zip", metavar="PATH", help="Путь к ZIP-архиву выгрузки")
    parser.add_argument("--workspace-id", type=int, required=True, help="ID workspace")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    await storage.get_db()
    try:
        if args.json:
            stats = await import_from_json(args.json, args.workspace_id)
        else:
            stats = await import_from_zip(args.zip, args.workspace_id)

        print(f"Готово. Добавлено: {stats['added']}, пропущено дублей: {stats['skipped']}")
    finally:
        await storage.close_db()


if __name__ == "__main__":
    asyncio.run(_cli_main())
