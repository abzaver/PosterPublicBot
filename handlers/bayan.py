import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

import storage

logger = logging.getLogger(__name__)


def _make_link(chat_id: int, msg_id: int) -> str:
    # chat_id для каналов и супергрупп: -100XXXXXXXXXX → убираем -100
    bare = str(chat_id).lstrip("-")
    if bare.startswith("100"):
        bare = bare[3:]
    return f"https://t.me/c/{bare}/{msg_id}"


async def check_bayan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    workspace_id: int,
    bot_msg_id: int,
    chat_id: int,
    phash: str,
) -> bool:
    """Проверяет баян и реагирует согласно on_bayan_action. Возвращает True если баян найден."""
    threshold = int(await storage.get_config(workspace_id, "hash_threshold"))
    results = await storage.search_images_by_hash(workspace_id, phash, threshold)

    candidates = [r for r in results if not (r["chat_id"] == chat_id and r["msg_id"] == bot_msg_id)]

    if not candidates:
        return False

    # Показываем что бот работает пока проверяем живость ссылок
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Проверяем живость только для сообщений в чатах где бот является участником
    # (АК и ОК текущего workspace). Записи из внешних каналов (датасет) считаем живыми.
    ws = await storage.get_workspace_by_ak(chat_id)
    bot_chat_ids = {chat_id}
    if ws and ws["ok_chat_id"]:
        bot_chat_ids.add(ws["ok_chat_id"])

    duplicates = []
    dead_ids = []
    for r in candidates:
        if r["chat_id"] not in bot_chat_ids:
            duplicates.append(r)
            continue
        try:
            probe = await context.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=r["chat_id"],
                message_id=r["msg_id"],
                disable_notification=True,
            )
            await context.bot.delete_message(chat_id=chat_id, message_id=probe.message_id)
            duplicates.append(r)
        except Exception as e:
            logger.info("Мёртвая ссылка image_id=%s msg_id=%s: %s", r["id"], r["msg_id"], e)
            dead_ids.append(r["id"])

    for dead_id in dead_ids:
        await storage.delete_image(dead_id)
    if dead_ids:
        logger.info("Удалено мёртвых записей: %d", len(dead_ids))

    if not duplicates:
        return False

    action = await storage.get_config(workspace_id, "on_bayan_action")

    links = " ".join(_make_link(r["chat_id"], r["msg_id"]) for r in duplicates)
    bayan_text = f"🪗 Баян! Уже было здесь: {links}"

    if action == "block":
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_msg_id)
        except Exception as e:
            logger.warning("Не удалось удалить баян-пост %s: %s", bot_msg_id, e)

        post = await storage.get_post_by_msg(workspace_id, bot_msg_id)
        if post and post["sender_user_id"]:
            try:
                await context.bot.send_message(
                    chat_id=post["sender_user_id"],
                    text=f"Твой пост не опубликован — баян.\n{links}",
                )
            except Exception:
                pass
    else:
        # Меняем caption поста на сообщение о баяне
        post = await storage.get_post_by_msg(workspace_id, bot_msg_id)
        from handlers.voting import build_caption_bayan
        full_caption = build_caption_bayan(
            post["caption"] if post else "",
            post["sender_name"] if post else "",
            links,
        )
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=bot_msg_id,
                caption=full_caption,
            )
        except Exception as e:
            logger.warning("Не удалось изменить caption: %s", e)
            # Фоллбэк — отдельное сообщение
            await context.bot.send_message(
                chat_id=chat_id,
                text=bayan_text,
                reply_to_message_id=bot_msg_id,
            )

    return True
