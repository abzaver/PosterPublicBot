import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, ChatMemberHandler, filters

import storage

logger = logging.getLogger(__name__)

ONBOARDING_INSTRUCTIONS = (
    "Привет! Чтобы подключить бота к своему каналу:\n\n"
    "1️⃣ Добавь меня в свою <b>админскую группу (АК)</b> и напиши там <code>/set_ak</code>\n"
    "2️⃣ Добавь меня в свой <b>основной канал (ОК)</b> как администратора — я привяжу его автоматически\n\n"
    "После этого бот будет готов к работе."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    workspaces = await storage.get_workspace_by_owner(user_id)

    if not workspaces:
        ws_id = await storage.create_workspace(owner_user_id=user_id)
        context.user_data["pending_workspace_id"] = ws_id
        await update.message.reply_html(ONBOARDING_INSTRUCTIONS)
    else:
        pending = [w for w in workspaces if w["status"] == "pending"]
        active = [w for w in workspaces if w["status"] == "active"]
        if pending:
            context.user_data["pending_workspace_id"] = pending[0]["id"]
            await update.message.reply_html(
                f"У тебя есть незавершённая настройка (workspace #{pending[0]['id']}).\n\n"
                + ONBOARDING_INSTRUCTIONS
            )
        else:
            lines = "\n".join(f"• #{w['id']} — активен" for w in active)
            await update.message.reply_html(
                f"У тебя уже есть {len(active)} активных workspace:\n{lines}\n\n"
                "Чтобы добавить новый, напиши /new_workspace"
            )


async def new_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    ws_id = await storage.create_workspace(owner_user_id=user_id)
    context.user_data["pending_workspace_id"] = ws_id
    await update.message.reply_html(
        f"Создан новый workspace #{ws_id}.\n\n" + ONBOARDING_INSTRUCTIONS
    )


async def set_ak(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Команду /set_ak нужно вызывать в группе (АК).")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    workspaces = await storage.get_workspace_by_owner(user_id)
    pending = [w for w in workspaces if w["status"] == "pending"]

    if not pending:
        # Создаём workspace автоматически — не требуем сначала идти в личку
        ws_id = await storage.create_workspace(owner_user_id=user_id)
        ws = (await storage.get_workspace_by_owner(user_id))[0]
    else:
        ws = pending[0]

    # Проверяем что этот чат ещё не привязан к другому workspace
    existing = await storage.get_workspace_by_ak(chat_id)
    if existing and existing["id"] != ws["id"]:
        await update.message.reply_text(
            "Эта группа уже привязана к другому workspace."
        )
        return

    await storage.set_workspace_ak(ws["id"], ak_chat_id=chat_id)

    # Проверяем активировался ли workspace
    updated = await storage.get_workspace_by_ak(chat_id)
    if updated and updated["status"] == "active":
        await update.message.reply_html(
            "✅ АК привязан! Workspace активен.\n"
            "Используй /config чтобы посмотреть настройки."
        )
    else:
        await update.message.reply_html(
            "✅ АК привязан!\n"
            "Теперь добавь меня в свой канал (ОК) как администратора — я привяжу его автоматически."
        )


async def set_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != "private":
        await update.message.reply_text("Команду /set_ok нужно вызывать в личке с ботом.")
        return

    if not context.args:
        await update.message.reply_text(
            "Укажи username или chat_id канала:\n"
            "/set_ok @my_channel\n"
            "/set_ok -1001234567890"
        )
        return

    user_id = update.effective_user.id
    arg = context.args[0]

    workspaces = await storage.get_workspace_by_owner(user_id)
    pending = [w for w in workspaces if w["status"] == "pending"]

    if not pending:
        await update.message.reply_text(
            "Нет незавершённой настройки. Напиши /new_workspace чтобы создать новый workspace."
        )
        return

    ws = pending[0]

    # Принимаем и @username, и числовой chat_id
    try:
        chat_ref = int(arg)
    except ValueError:
        chat_ref = f"@{arg.lstrip('@')}"

    try:
        chat = await context.bot.get_chat(chat_ref)
        ok_chat_id = chat.id
        ok_title = chat.title or str(ok_chat_id)
    except Exception:
        await update.message.reply_text(
            f"Не могу найти канал {arg}.\n"
            "Убедись что бот добавлен в канал и попробуй передать числовой chat_id."
        )
        return

    bot_member = None
    try:
        bot_member = await context.bot.get_chat_member(ok_chat_id, context.bot.id)
    except Exception:
        pass

    await storage.set_workspace_ok(ws["id"], ok_chat_id=ok_chat_id)

    # Перечитываем workspace чтобы узнать реальный статус после попытки активации
    updated_workspaces = await storage.get_workspace_by_owner(user_id)
    updated_ws = next((w for w in updated_workspaces if w["id"] == ws["id"]), None)
    is_active = updated_ws and updated_ws["status"] == "active"

    has_rights = bot_member and bot_member.status in ("administrator", "creator")

    if not has_rights:
        await update.message.reply_html(
            f"✅ ОК <b>{ok_title}</b> сохранён, но <b>бот не является администратором канала</b>.\n"
            "Добавь бота как администратора, иначе публикация не заработает."
        )
    elif is_active:
        await update.message.reply_html(
            f"✅ Workspace активен!\n\n"
            f"АК и ОК <b>{ok_title}</b> подключены. Бот готов к работе.\n"
            "Напиши /config чтобы посмотреть настройки."
        )
    else:
        await update.message.reply_html(
            f"✅ ОК <b>{ok_title}</b> сохранён.\n\n"
            "Ещё нужно привязать АК — добавь бота в свою админскую группу и напиши там <code>/set_ak</code>"
        )


async def on_bot_added_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Срабатывает когда бота добавляют/убирают из канала."""
    result = update.my_chat_member
    if not result:
        return

    chat = result.chat
    if chat.type != "channel":
        return

    new_status = result.new_chat_member.status
    if new_status not in ("administrator", "creator"):
        return

    # Бота добавили в канал как администратора — сообщаем добавившему
    added_by = result.from_user
    if not added_by:
        return

    workspaces = await storage.get_workspace_by_owner(added_by.id)
    pending = [w for w in workspaces if w["status"] == "pending" and w["ak_chat_id"]]

    if not pending:
        # Нет pending workspace с АК — просто подсказываем
        try:
            await context.bot.send_message(
                chat_id=added_by.id,
                text=(
                    f"Я добавлен в канал <b>{chat.title}</b> (id: <code>{chat.id}</code>).\n"
                    "Чтобы привязать его как ОК, напиши:\n"
                    f"<code>/set_ok {chat.id}</code>"
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    ws = pending[0]
    await storage.set_workspace_ok(ws["id"], ok_chat_id=chat.id)

    updated = await storage.get_workspace_by_owner(added_by.id)
    updated_ws = next((w for w in updated if w["id"] == ws["id"]), None)
    is_active = updated_ws and updated_ws["status"] == "active"

    try:
        if is_active:
            await context.bot.send_message(
                chat_id=added_by.id,
                text=(
                    f"✅ Workspace активен!\n\n"
                    f"ОК <b>{chat.title}</b> автоматически привязан. Бот готов к работе.\n"
                    "Напиши /config чтобы посмотреть настройки."
                ),
                parse_mode="HTML",
            )
        else:
            await context.bot.send_message(
                chat_id=added_by.id,
                text=(
                    f"✅ ОК <b>{chat.title}</b> сохранён.\n\n"
                    "Ещё нужно привязать АК — добавь бота в свою админскую группу и напиши там <code>/set_ak</code>"
                ),
                parse_mode="HTML",
            )
    except Exception:
        pass


async def show_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_type = update.effective_chat.type

    ws = None
    if chat_type == "private":
        user_id = update.effective_user.id
        workspaces = await storage.get_workspace_by_owner(user_id)
        active = [w for w in workspaces if w["status"] == "active"]
        if not active:
            await update.message.reply_text("Нет активных workspace. Напиши /start для настройки.")
            return
        ws = active[0]
    elif chat_type in ("group", "supergroup"):
        ws = await storage.get_workspace_by_ak(update.effective_chat.id)
        if not ws:
            await update.message.reply_text("Эта группа не привязана ни к одному workspace.")
            return
    else:
        return

    cfg = await storage.get_all_config(ws["id"])
    lines = [f"<b>Workspace #{ws['id']}</b>", ""]
    lines.append(f"Порог баяна (Hamming): <code>{cfg['hash_threshold']}</code>")
    lines.append(f"Порог голосов: <code>{cfg['vote_threshold']}</code>")
    lines.append(f"Автопубликация: <code>{cfg['autopublish']}</code>")
    lines.append(f"При баяне: <code>{cfg['on_bayan_action']}</code>")
    lines.append(f"Gotcha: <code>{cfg['gotcha']}</code>")
    lines.append(f"Положительные реакции: {cfg['positive_reactions']}")
    lines.append(f"Отрицательные реакции: {cfg['negative_reactions']}")

    await update.message.reply_html("\n".join(lines))


def register(application) -> None:
    application.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("new_workspace", new_workspace, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("set_ok", set_ok, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("set_ak", set_ak, filters=filters.ChatType.GROUPS))
    application.add_handler(CommandHandler("config", show_config))
    application.add_handler(ChatMemberHandler(on_bot_added_to_channel, ChatMemberHandler.MY_CHAT_MEMBER))
