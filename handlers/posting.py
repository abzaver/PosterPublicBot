import logging
import tempfile
from pathlib import Path

from telegram import Update, Message, ReactionTypeEmoji
from telegram.constants import ChatAction
from telegram.ext import ContextTypes, MessageHandler, CommandHandler, filters

import storage
import image_hash
from handlers.bayan import check_bayan
from handlers.voting import build_caption, build_caption_short, _sender_name

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
    original_caption = message.caption or ""
    sender_name = _sender_name(update.effective_user) if update.effective_user else "аноним"
    caption = build_caption_short(original_caption, sender_name)

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

    action = ChatAction.UPLOAD_PHOTO if media_type == "photo" else ChatAction.UPLOAD_VIDEO
    await context.bot.send_chat_action(chat_id=chat_id, action=action)

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
        caption=original_caption,
        sender_name=sender_name,
    )
    await storage.add_image(
        workspace_id=ws["id"],
        chat_id=chat_id,
        phash=phash,
        msg_id=sent.message_id,
    )

    is_bayan = await check_bayan(update, context, ws["id"], sent.message_id, chat_id, phash)

    if not is_bayan:
        positive_r = await storage.get_config(ws["id"], "positive_reactions")
        negative_r = await storage.get_config(ws["id"], "negative_reactions")
        full_caption = build_caption(original_caption, sender_name, positive_r, negative_r)
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=sent.message_id,
                caption=full_caption,
            )
        except Exception as e:
            logger.warning("Не удалось обновить caption: %s", e)
        try:
            await context.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=sent.message_id,
                reaction=[ReactionTypeEmoji(emoji="👍")],
            )
            await storage.upsert_vote(
                workspace_id=ws["id"],
                post_id=post_id,
                user_id=context.bot.id,
                reaction="👍",
            )
        except Exception as e:
            logger.warning("Не удалось поставить реакцию: %s", e)

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
