import logging
import tempfile
from pathlib import Path

from telegram import Update, Message
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

import storage
import image_hash

logger = logging.getLogger(__name__)


async def _get_ak_workspace(chat_id: int) -> storage.aiosqlite.Row | None:
    return await storage.get_workspace_by_ak(chat_id)


async def _delete_original(message: Message) -> None:
    try:
        await message.delete()
    except Exception as e:
        logger.warning("Не удалось удалить сообщение %s: %s", message.message_id, e)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat_id = update.effective_chat.id

    ws = await _get_ak_workspace(chat_id)
    if not ws:
        return

    sender_id = update.effective_user.id if update.effective_user else None
    caption = message.caption or ""

    # Определяем тип медиа и скачиваем
    if message.photo:
        media_type = "photo"
        file = await context.bot.get_file(message.photo[-1].file_id)
    elif message.animation:
        media_type = "animation"
        file = await context.bot.get_file(message.animation.file_id)
    elif message.video:
        media_type = "video"
        file = await context.bot.get_file(message.video.file_id)
    else:
        return

    await _delete_original(message)

    # Скачиваем во временный файл для хэширования
    suffix = ".jpg" if media_type == "photo" else ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        tmp_path = f.name
    try:
        await file.download_to_drive(tmp_path)

        if media_type == "photo":
            phash = await image_hash.phash_from_file(tmp_path)
        else:
            phash = await image_hash.phash_from_animation(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Перепостим от имени бота
    if media_type == "photo":
        sent = await context.bot.send_photo(
            chat_id=chat_id,
            photo=message.photo[-1].file_id,
            caption=caption,
        )
    elif media_type == "animation":
        sent = await context.bot.send_animation(
            chat_id=chat_id,
            animation=message.animation.file_id,
            caption=caption,
        )
    else:
        sent = await context.bot.send_video(
            chat_id=chat_id,
            video=message.video.file_id,
            caption=caption,
        )

    # Сохраняем пост и хэш
    post_id = await storage.add_post(
        workspace_id=ws["id"],
        bot_msg_id=sent.message_id,
        chat_id=chat_id,
        sender_user_id=sender_id,
        media_type=media_type,
    )
    await storage.add_image(
        workspace_id=ws["id"],
        chat_id=chat_id,
        phash=phash,
        msg_id=sent.message_id,
    )

    logger.info("АК пост #%s сохранён (workspace %s, phash %s)", post_id, ws["id"], phash)


async def handle_mem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat_id = update.effective_chat.id

    ws = await _get_ak_workspace(chat_id)
    if not ws:
        return

    if not context.args:
        await message.reply_text("Использование: /mem <текст>")
        return

    text = " ".join(context.args)
    sender_id = update.effective_user.id if update.effective_user else None

    await _delete_original(message)

    sent = await context.bot.send_message(chat_id=chat_id, text=text)

    await storage.add_post(
        workspace_id=ws["id"],
        bot_msg_id=sent.message_id,
        chat_id=chat_id,
        sender_user_id=sender_id,
        media_type="text",
    )

    logger.info("АК текст опубликован (workspace %s)", ws["id"])


async def handle_ok_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сохраняет хэши медиа из ОК в БД (без уведомлений)."""
    message = update.effective_message
    chat_id = update.effective_chat.id

    ws = await storage.get_workspace_by_ok(chat_id)
    if not ws:
        return

    if message.photo:
        file = await context.bot.get_file(message.photo[-1].file_id)
        suffix = ".jpg"
        media_type = "photo"
    elif message.animation:
        file = await context.bot.get_file(message.animation.file_id)
        suffix = ".mp4"
        media_type = "animation"
    elif message.video:
        file = await context.bot.get_file(message.video.file_id)
        suffix = ".mp4"
        media_type = "video"
    else:
        return

    # Проверяем дубль по msg_id чтобы не хэшировать повторно
    if await storage.image_exists(ws["id"], chat_id, message.message_id):
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        tmp_path = f.name
    try:
        await file.download_to_drive(tmp_path)
        if media_type == "photo":
            phash = await image_hash.phash_from_file(tmp_path)
        else:
            phash = await image_hash.phash_from_animation(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    await storage.add_image(
        workspace_id=ws["id"],
        chat_id=chat_id,
        phash=phash,
        msg_id=message.message_id,
    )
    logger.info("ОК медиа сохранено (workspace %s, msg %s)", ws["id"], message.message_id)


def register(application) -> None:
    media_filter = filters.PHOTO | filters.ANIMATION | filters.VIDEO

    # АК: перехват медиа
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & media_filter & ~filters.COMMAND,
        handle_media,
    ))
    # АК: команда /mem
    application.add_handler(CommandHandler(
        "mem", handle_mem, filters=filters.ChatType.GROUPS,
    ))
    # ОК: тихое сохранение медиа
    application.add_handler(MessageHandler(
        filters.ChatType.CHANNEL & media_filter,
        handle_ok_media,
    ))
