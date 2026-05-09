#!/usr/bin/env python
import logging
import os

from telegram import Update
from telegram.ext import Application

import storage
import handlers.onboarding as onboarding

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

token = os.getenv("TLG_TOKEN")


async def on_startup(application: Application) -> None:
    await storage.get_db()
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

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
