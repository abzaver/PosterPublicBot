#!/usr/bin/env python
import logging
import os

from telegram import Update, BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
from telegram.ext import Application

import storage
import handlers.onboarding as onboarding
import handlers.posting as posting
import handlers.voting as voting

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

token = os.getenv("TLG_TOKEN")


async def on_startup(application: Application) -> None:
    await storage.get_db()

    await application.bot.set_my_commands(
        [
            BotCommand("start", "Начать настройку / статус workspace"),
            BotCommand("my_workspaces", "Список моих workspace"),
            BotCommand("new_workspace", "Создать новый workspace"),
            BotCommand("delete_workspace", "Удалить workspace"),
            BotCommand("config", "Настройки текущего workspace"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await application.bot.set_my_commands(
        [
            BotCommand("set_ak", "Привязать эту группу как АК"),
            BotCommand("config", "Настройки текущего workspace"),
            BotCommand("mem", "Опубликовать текст от имени бота"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )

    logger.info("Bot started")


async def on_shutdown(application: Application) -> None:
    await storage.close_db()
    logger.info("Bot stopped")


def main() -> None:
    application = (
        Application.builder()
        .token(token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    onboarding.register(application)
    posting.register(application)
    voting.register(application)

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
