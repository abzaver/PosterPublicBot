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

import logging
import os

from telegram import __version__ as TG_VER, MessageEntity

import hamming_db as ham_dist

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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, MessageReactionHandler

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


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    #await update.message.reply_text(update.message.text)
    #await update.message.set_reaction(reaction=ReactionTypeEmoji(ReactionEmoji.THUMBS_UP))
    #"""Echo the user message."""
    #return

    #https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a
    user_entities = update.message.parse_entities(
        [MessageEntity.MENTION, MessageEntity.TEXT_MENTION]
    )
    if context.bot.name in user_entities.values():
        msg_text = 'Hey, @' + str(update.effective_user.username) + '!'
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg_text,
                                       reply_to_message_id=update.message.message_id)
    #print("message id:", update.message.forward_from_message_id, " chat_id:", update.message.forward_from_chat.id)

    if update.message.photo:
        #await context.bot.send_message(chat_id=update.effective_chat.id, text="I see photo in this message!", reply_to_message_id=update.message.message_id)
        file_id = update.message.photo[-1].file_id
        new_file = await context.bot.get_file(file_id)
        await new_file.download_to_drive('img_to_search')
        ham_db_conn = ham_dist.create_or_open_db(ham_dist.DATABASE_NAME)
        search_results = ham_dist.search_by_image(ham_db_conn, 'img_to_search', 10)
        if search_results:
            for result in search_results:
                if result[1] == 1242081849:  # if it's chat then it's "progressive memes"
                    chat = await context.bot.get_chat('@progressive_memes')
                    link_to_message = f'Dude, this is \N{accordion}! It was there: t.me/progressive_memes/{result[3]}'
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                   text=link_to_message,
                                                   reply_to_message_id=update.message.message_id)
                    #await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=chat.id, message_id={result[3]})
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id,
                                                   text='Dude, I was see this in another chats, but I can''t remember where...',
                                                   reply_to_message_id=update.message.message_id)
                    #chat = await context.bot.get_chat('@progressive_memes')
                    #logger.info(chat)
                    #await context.bot.forward_message(chat_id=update.effective_chat.id, from_chat_id=result[1], message_id=result[3])
                    #await context.bot.send_message(chat_id=update.effective_chat.id,
                    #                               text=f"Чувак, это \N{accordion}! message id: {result[3]} from chat id: {result[1]}, date {datetime.datetime.fromtimestamp(result[4])}",
                    #                               reply_to_message_id=update.message.message_id)
        else:
            await update.message.reply_text('Wow! Something new!!!')
        ham_db_conn.close()


async def reaction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg_reaction = update.message_reaction
    if len(msg_reaction.new_reaction) != 0 and len(msg_reaction.old_reaction) == 0:
        logger.info("This is new reaction %s", msg_reaction.new_reaction[0].emoji)
    elif len(msg_reaction.new_reaction) != 0 and len(msg_reaction.old_reaction) != 0:
        logger.info("Reaction is changed from %s, to %s", msg_reaction.old_reaction[0].emoji,
                    msg_reaction.new_reaction[0].emoji)
    else:
        logger.info("Reaction removed: %s", msg_reaction.message_id)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(token).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO & ~filters.COMMAND, echo))
    application.add_handler(MessageReactionHandler(reaction_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
