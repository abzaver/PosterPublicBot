import logging

from telegram import Update
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

    # Исключаем только что добавленное сообщение из результатов
    duplicates = [r for r in results if not (r["chat_id"] == chat_id and r["msg_id"] == bot_msg_id)]

    if not duplicates:
        return False

    action = await storage.get_config(workspace_id, "on_bayan_action")

    links = " ".join(_make_link(r["chat_id"], r["msg_id"]) for r in duplicates)
    text = f"🪗 Баян! Уже было здесь: {links}"

    if action == "block":
        # Удаляем пост бота
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bot_msg_id)
        except Exception as e:
            logger.warning("Не удалось удалить баян-пост %s: %s", bot_msg_id, e)

        # Уведомляем постера в личку
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
        # warn или warn_no_vote — отвечаем реплаем на пост бота
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=bot_msg_id,
        )

    return True
