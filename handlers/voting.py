import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, MessageReactionHandler, CallbackQueryHandler

import storage

logger = logging.getLogger(__name__)

PUBLISH_CALLBACK = "publish:"
CAPTION_SEPARATOR = "\n\n—"


def build_caption(original: str, sender_name: str, positive: str = "👍 ❤ 🔥", negative: str = "👎 💩") -> str:
    suffix = (
        f"Прислал: {sender_name}\n"
        f"Голосуй реакциями: {positive} — за, {negative} — против.\n"
        f"Если одобрений больше — опубликуем в канале!"
    )
    if original:
        return f"{original}{CAPTION_SEPARATOR} {suffix}"
    return f"{CAPTION_SEPARATOR} {suffix}"


def build_caption_short(original: str, sender_name: str) -> str:
    suffix = f"Прислал: {sender_name}"
    if original:
        return f"{original}{CAPTION_SEPARATOR} {suffix}"
    return f"{CAPTION_SEPARATOR} {suffix}"


def build_caption_bayan(original: str, sender_name: str, links: str) -> str:
    suffix = f"Прислал: {sender_name}\n🪗 Баян! Уже было здесь: {links}"
    if original:
        return f"{original}{CAPTION_SEPARATOR} {suffix}"
    return f"{CAPTION_SEPARATOR} {suffix}"


def strip_caption(caption: str) -> str:
    idx = caption.find(CAPTION_SEPARATOR)
    return caption[:idx].strip() if idx != -1 else caption.strip()


def _sender_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name.strip() or "аноним"


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    r = update.message_reaction
    if not r or not r.user:
        return

    chat_id = r.chat.id
    ws = await storage.get_workspace_by_ak(chat_id)
    if not ws:
        return

    workspace_id = ws["id"]
    msg_id = r.message_id
    user_id = r.user.id

    post = await storage.get_post_by_msg(workspace_id, msg_id)
    if not post:
        return

    positive_str = await storage.get_config(workspace_id, "positive_reactions")
    positive_set = set(positive_str.split())

    new_emojis = {re.emoji for re in r.new_reaction} if r.new_reaction else set()
    old_emojis = {re.emoji for re in r.old_reaction} if r.old_reaction else set()

    # Gotcha: пост уже опубликован, пользователь меняет реакцию
    if post["status"] == "published" and old_emojis and new_emojis:
        gotcha = await storage.get_config(workspace_id, "gotcha")
        if gotcha == "on":
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Поздно, уже в канале 😏",
                    reply_to_message_id=msg_id,
                )
            except Exception:
                pass
        return

    # Обновляем голос в БД
    if new_emojis:
        emoji = next(iter(new_emojis))
        await storage.upsert_vote(workspace_id, post["id"], user_id, emoji)
    else:
        await storage.delete_vote(post["id"], user_id)

    # Пересчитываем
    threshold = int(await storage.get_config(workspace_id, "vote_threshold"))
    positive, negative = await storage.count_votes(post["id"], list(positive_set))
    score = positive - negative

    if post["status"] == "pending":
        if score >= threshold:
            autopublish = await storage.get_config(workspace_id, "autopublish")
            if autopublish == "on":
                await _publish(context, ws, post, chat_id)
                return
            label = "📢 Опубликовать в ОК"
            callback = f"{PUBLISH_CALLBACK}{post['id']}"
        else:
            label = f"🚫 Не одобрено (👍 {positive} · 👎 {negative})"
            callback = f"rejected:{post['id']}"

        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=callback)]])
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=post["bot_msg_id"],
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning("Не удалось обновить кнопку: %s", e)


async def handle_publish_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    post_id = int(query.data[len(PUBLISH_CALLBACK):])
    chat_id = update.effective_chat.id

    ws = await storage.get_workspace_by_ak(chat_id)
    if not ws:
        return

    post = await storage.get_post_by_msg(ws["id"], query.message.message_id)
    if not post or post["id"] != post_id:
        return

    if post["status"] == "published":
        await query.answer("Уже опубликовано!", show_alert=False)
        return

    await _publish(context, ws, post, chat_id, query=query)


async def _publish(context, ws, post, ak_chat_id: int, query=None) -> None:
    ok_chat_id = ws["ok_chat_id"]
    if not ok_chat_id:
        logger.warning("ОК не привязан для workspace %s", ws["id"])
        return

    try:
        sent = await context.bot.copy_message(
            chat_id=ok_chat_id,
            from_chat_id=ak_chat_id,
            message_id=post["bot_msg_id"],
            caption=post["caption"] or "",
        )
    except Exception as e:
        logger.error("Ошибка публикации в ОК: %s", e)
        return

    published = await storage.mark_post_published(post["id"], sent.message_id)
    if not published:
        try:
            await context.bot.delete_message(chat_id=ok_chat_id, message_id=sent.message_id)
        except Exception:
            pass
        return

    # Сохраняем хэш в ОК — бот не получает свои собственные сообщения как updates
    img = await storage.get_image_by_msg(ws["id"], ak_chat_id, post["bot_msg_id"])
    if img:
        await storage.add_image(
            workspace_id=ws["id"],
            chat_id=ok_chat_id,
            phash=img["phash"],
            msg_id=sent.message_id,
        )

    ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ Опубликовано в ОК {ts}", callback_data=f"published:{post['id']}")
    ]])
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=ak_chat_id,
            message_id=post["bot_msg_id"],
            reply_markup=keyboard,
        )
    except Exception:
        pass

    logger.info("Пост %s опубликован в ОК (workspace %s)", post["id"], ws["id"])


async def handle_noop_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()


def register(application) -> None:
    application.add_handler(MessageReactionHandler(handle_reaction))
    application.add_handler(CallbackQueryHandler(handle_publish_button, pattern=f"^{PUBLISH_CALLBACK}"))
    application.add_handler(CallbackQueryHandler(handle_noop_button, pattern=r"^(published:|rejected:)"))
