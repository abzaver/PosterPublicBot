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
from telegram import ForceReply, Update, Chat
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
    if update.effective_chat.type == Chat.CHANNEL:
        return
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=False),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    if update.effective_chat.type == Chat.CHANNEL:
        return
    await update.message.reply_text("Help!")


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """reply the user message, but only if bot mentioned"""
    if update.effective_chat.type == Chat.CHANNEL:
        return
    message_entities = update.effective_message.parse_entities(
        [MessageEntity.MENTION, MessageEntity.TEXT_MENTION]
    )
    if context.bot.name in message_entities.values():
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f'Привет, {update.effective_user.username}! Чего хотел?',
                                       reply_to_message_id=update.effective_message.message_id)
    #print("message id:", update.message.forward_from_message_id, " chat_id:", update.message.forward_from_chat.id)

async def process_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """trying to process the received photo"""
    #await context.bot.send_message(chat_id=update.effective_chat.id, text="I see photo in this message!", reply_to_message_id=update.message.message_id)
    file_id = update.effective_message.photo[-1].file_id
    new_file = await context.bot.get_file(file_id)
    await new_file.download_to_drive('./data/img_to_search')
    ham_db_conn = ham_dist.create_or_open_db(ham_dist.DATABASE_NAME)
    search_results = ham_dist.search_by_image(ham_db_conn, './data/img_to_search', 10)
    if search_results:
        reply_msg = f'Чувак, это \N{accordion}! '
        for result in search_results:
            if result[1] == 1242081849:  # если чат это "прогрессивные мемы"
                chat = await context.bot.get_chat('@progressive_memes')
                reply_msg += f'Было здесь: t.me/progressive_memes/{result[3]}. '
            else:
                reply_msg += f' Было в чате {result[1]}, примерно {datetime.datetime.fromtimestamp(result[4])}. '

                #await context.bot.send_message(chat_id=update.effective_chat.id, text='Я видел это в других чатах, но не могу сказать точно в каком сообщении',
                #                               reply_to_message_id=update.message.message_id)
                #chat = await context.bot.get_chat('@progressive_memes')
                #logger.info(chat)
                #await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=result[1], message_id=result[3])
                #await context.bot.send_message(chat_id=update.effective_chat.id,
                #                               text=f"Чувак, это \N{accordion}! message id: {result[3]} from chat id: {result[1]}, date {datetime.datetime.fromtimestamp(result[4])}",
                #                               reply_to_message_id=update.message.message_id)
    else:
        reply_msg = ('Ух ты! Что-то новенькое!')
        imgs_tuple_list = [tuple((update.effective_chat.id, str('./data/img_to_search'), update.effective_message.message_id,
                                  int(update.effective_message.date.timestamp()), ''))]
        ham_dist.add_images_by_path(ham_db_conn, imgs_tuple_list)
        ham_dist.add_chat_to_db(ham_db_conn, [update.effective_chat.id, update.effective_chat.title, update.effective_chat.type])
    ham_db_conn.close()
    if update.effective_chat.type != Chat.CHANNEL:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=reply_msg,
                                       reply_to_message_id=update.effective_message.message_id)


async def process_animation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """trying to process the received animation"""
    file_name = './data/animation_to_search'
    file_id = update.effective_message.effective_attachment.file_id

    try:
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive(file_name)
    except BaseException as e:
        logger.info(e)
        if update.effective_chat.type != Chat.CHANNEL:
            await update.effective_message.reply_text('Слишком большой файл для меня... \N{Neutral face}')
        return

    ham_db_conn = ham_dist.create_or_open_db(ham_dist.DATABASE_NAME)
    hash_img_to_search = ham_dist.animation_to_hash(file_name)
    search_results = ham_dist.search_by_image_hash(ham_db_conn, hash_img_to_search, 10)
    if search_results:
        reply_msg = f"Чувак, это \N{accordion}!"
        for result in search_results:
            reply_msg += f" Было в чате {result[1]}, примерно {datetime.datetime.fromtimestamp(result[4])}. "
    else:
        reply_msg = 'Ух ты! Что-то новенькое!'
        imgs_tuple_list = [tuple((update.effective_chat.id, str(hash_img_to_search), update.effective_message.message_id,
                                  int(update.effective_message.date.timestamp()), ''))]
        ham_dist.add_images_by_hash(ham_db_conn, imgs_tuple_list)
        ham_dist.add_chat_to_db(ham_db_conn, [update.effective_chat.id, update.effective_chat.title, update.effective_chat.type])
    ham_db_conn.close()
    if update.effective_chat.type != Chat.CHANNEL:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=reply_msg,
                                       reply_to_message_id=update.effective_message.message_id)


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
    application.add_handler(MessageHandler((filters.Document.GIF | filters.Document.MP4 | filters.VIDEO) & ~filters.COMMAND, process_animation))

    # Run the bot until the user presses Ctrl-C
    application.run_polling()


if __name__ == "__main__":
    main()
