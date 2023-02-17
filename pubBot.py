#!/usr/bin/env python
# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import hamming_db as ham_dist
import datetime

import logging
import os

from telegram import __version__ as TG_VER, MessageEntity

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

token = os.getenv("TLG_TOKEN")


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """reply the user message, but only if bot mentioned"""
    message_entities = update.message.parse_entities(
        [MessageEntity.MENTION, MessageEntity.TEXT_MENTION]
    )
    if context.bot.name in message_entities.values():
        await context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text,
                                       reply_to_message_id=update.message.message_id)
    #print("message id:", update.message.forward_from_message_id, " chat_id:", update.message.forward_from_chat.id)

async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """trying to process the recieved photo"""
        #await context.bot.send_message(chat_id=update.effective_chat.id, text="I see photo in this message!", reply_to_message_id=update.message.message_id)
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive('./data/img_to_search')
        ham_db_conn = ham_dist.create_or_open_db(ham_dist.DATABASE_NAME)
        search_results = ham_dist.search_by_image(ham_db_conn, './data/img_to_search', 10)
        if search_results:
            for result in search_results:
                if result[1] == 1242081849:  # если чат это "прогрессивные мемы"
                    chat = await context.bot.get_chat('@progressive_memes')
                    link_to_message = f'Чувак, это \N{accordion}! Было здесь: t.me/progressive_memes/{result[3]}'
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                               text=link_to_message,
                                               reply_to_message_id=update.message.message_id)
                    #await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=chat.id, message_id={result[3]})
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text='Я видел это в других чатах, но не могу сказать точно в каком сообщении',
                                                   reply_to_message_id=update.message.message_id)
                    #chat = await context.bot.get_chat('@progressive_memes')
                    #logger.info(chat)
                    #await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=result[1], message_id=result[3])
                    #await context.bot.send_message(chat_id=update.effective_chat.id,
                    #                               text=f"Чувак, это \N{accordion}! message id: {result[3]} from chat id: {result[1]}, date {datetime.datetime.fromtimestamp(result[4])}",
                    #                               reply_to_message_id=update.message.message_id)
        else:
            await update.message.reply_text('Ух ты! Что-то новенькое!')
        ham_db_conn.close()


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, process_photo))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
