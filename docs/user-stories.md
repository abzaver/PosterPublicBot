# User Stories: PosterPublicBot

## Эпик E-1: Детектор баяна

### US-1.1 — Оповещение о баяне в АК
> **As an** admin posting in АК,  
> **I want** the bot to tell me if the image was already posted,  
> **so that** I don't flood the channel with duplicates.

**Acceptance Criteria:**
- [ ] Бот проверяет только медиа в АК (в ОК баян не проверяется).
- [ ] Бот отвечает реплаем на свой же пост в АК в течение 5 секунд.
- [ ] Ответ — список ссылок на все найденные похожие сообщения (из ОК и АК одинаково).
- [ ] Если похожих нет — бот молчит (не засоряет чат).
- [ ] Порог похожести берётся из конфигурации.
- [ ] Поведение при обнаружении баяна настраивается параметром `on_baян_action`:
  - `warn` (по умолчанию) — перепостить и предупредить, голосование идёт.
  - `block` — не перепостить, удалить оригинал, сообщить постеру в личку.
  - `warn_no_vote` — перепостить и предупредить, но кнопку голосования не добавлять.

---

### US-1.2 — Сохранение медиа из АК и ОК + детектор GIF/видео
> **When** a photo, GIF, or video is posted in АК or ОК,  
> **I want** the bot to silently save its hash and detect duplicates for all media types,  
> **so that** future duplicate checks cover all content from both channels.

**Acceptance Criteria:**
- [ ] Каждое новое фото в АК сохраняется в БД (chat_id + message_id + hash).
- [ ] Каждое новое фото в ОК сохраняется в БД (всё, что появляется в канале).
- [ ] GIF (Animation) сохраняется и проверяется на дубль через `animation_to_hash`.
- [ ] Видео сохраняется и проверяется аналогично GIF.
- [ ] Сохранение и хэширование не блокируют event loop (`asyncio.to_thread`).
- [ ] При нахождении дубля GIF/видео — ответ в том же формате, что и для фото.

---

### US-1.3 — Импорт истории канала из выгрузки Telegram
> **As a** workspace owner,  
> **I want** to seed the bot's database with past posts from my channels,  
> **so that** the bot can detect duplicates from day one, not just from the moment it was added.

**Acceptance Criteria:**
- [ ] Владелец workspace может отправить ZIP-архив выгрузки Telegram Desktop боту в личку — бот его распаковывает и импортирует хэши изображений.
- [ ] Бот сообщает прогресс и итог: сколько записей добавлено, сколько пропущено (дубли).
- [ ] Импортированные записи привязываются к workspace отправителя и нужному каналу (ОК или АК — уточняется при отправке).
- [ ] Доступен также CLI-скрипт `import_history.py` для запуска оператором на сервере (обёртка над существующим `parse_telegram_from_json`).
- [ ] Повторный импорт той же выгрузки не создаёт дублей в БД.

---

## Эпик E-2: Голосование и публикация

### US-2.0 — Бот как единственный постер в АК
> **When** an admin sends any media or text in АК,  
> **I want** the bot to immediately repost it on behalf of itself and delete the original,  
> **so that** all posts in АК are anonymous and uniform.

**Acceptance Criteria:**
- [ ] При получении фото/GIF/видео в АК бот немедленно удаляет оригинал и публикует медиа от своего имени (с оригинальным caption, если был).
- [ ] При получении текста через команду `/mem <текст>` — бот удаляет команду и публикует текст от своего имени.
- [ ] Личность постера в АК нигде не раскрывается.
- [ ] Бот сохраняет соответствие оригинальный отправитель → message_id поста бота в БД (для внутренней аналитики, не отображается).

---

### US-2.1 — Голосование реакциями
> **As an** admin,  
> **I want** to vote on a post in АК by reacting to it,  
> **so that** the team collectively decides what goes to ОК.

**Acceptance Criteria:**
- [ ] Бот отслеживает реакции только на медиа-посты в АК (фото, GIF, видео, текст через `/mem`). Служебные сообщения бота (баян, «опубликовано») — игнорируются.
- [ ] Учитываются только реакции из настроенных списков (положительные / отрицательные).
- [ ] Реакции самого бота не учитываются.
- [ ] Один участник АК — один голос (Telegram сам обеспечивает смену реакции; в платной версии несколько реакций возможны, но засчитывается только первая из списка настроенных).

---

### US-2.1b — «Gotcha»: оповещение о смене реакции в АК
> **When** an admin changes their reaction on a post in АК,  
> **I want** the bot to call them out publicly,  
> **so that** the team sees who flip-flopped and why.

**Acceptance Criteria:**
- [ ] Бот отслеживает смену реакции на медиа-постах в АК (было X → стало Y).
- [ ] При смене реакции бот отвечает реплаем на пост: «@username, чо поменял [X] на [Y]? 👀»
- [ ] Текст оповещения настраивается параметром `gotcha_template` (с плейсхолдерами `{user}`, `{old}`, `{new}`).
- [ ] Функция включается/выключается командой `/set_gotcha on|off` (по умолчанию `off`).
- [ ] Срабатывает только в АК, не в ОК.

---

### US-2.2 — Кнопка «ОТПРАВИТЬ В ОК»
> **As an** admin,  
> **I want** a button to appear on a post when it has enough votes,  
> **so that** I can publish it to ОК with one tap.

**Acceptance Criteria:**
- [ ] При достижении порога положительных голосов бот добавляет к своему сообщению inline-кнопку **[ОТПРАВИТЬ В ОК]**.
- [ ] При нажатии кнопки бот отправляет в ОК: медиа/текст + оригинальный caption (не forward, анонимно).
- [ ] Кнопка заменяется на «✅ Опубликовано» и становится неактивной.
- [ ] Повторное нажатие не создаёт дубль в ОК.
- [ ] Состояние кнопки сохраняется в БД и восстанавливается после рестарта.

---

### US-2.3 — Автопубликация
> **When** autopublish is enabled and a post reaches the vote threshold,  
> **I want** the bot to publish it to ОК automatically,  
> **so that** admins don't need to press a button.

**Acceptance Criteria:**
- [ ] Если `autopublish = on`, публикация в ОК происходит без нажатия кнопки.
- [ ] Бот помечает своё сообщение в АК как «✅ Опубликовано».
- [ ] Публикация необратима: последующее снятие реакций счётчик не меняет и публикацию не отменяет.
- [ ] Функция включается/выключается командой `/set_autopublish`.

---

## Эпик E-3: Конфигурация

### US-3.1 — Регистрация каналов
> **As an** admin setting up the bot,  
> **I want** to tell the bot which channels are ОК and АК,  
> **so that** it knows where to listen and where to publish.

**Acceptance Criteria:**
- [ ] `/set_ok @channel` — бот сохраняет ОК в конфиг; если у бота нет прав в канале — сохраняет, но предупреждает: «Добавь меня в канал, иначе публикация не заработает».
- [ ] `/set_ak` (вызов в нужном чате) — только владелец workspace (тот, кто делал `/start`) может привязать АК.
- [ ] При попытке вызова `/set_ak` не-владельцем — бот отказывает.
- [ ] Текущая конфигурация видна командой `/config`.

---

### US-3.2 — Настройка параметров голосования и детекции
> **As an** admin,  
> **I want** to tune thresholds and reaction lists,  
> **so that** the bot matches our team's workflow.

**Acceptance Criteria:**
- [ ] `/set_hash_threshold N` — меняет порог Hamming distance.
- [ ] `/set_positive_reactions 👍 ❤️ 🔥` и `/set_negative_reactions 👎 💩` — принимают стандартные эмодзи через пробел, сохраняют список. *(Формат команды уточняется после реализации.)*
- [ ] `/set_vote_threshold N` — меняет минимальное количество голосов для публикации.
- [ ] Все параметры хранятся в БД и выживают рестарт.
- [ ] `/config` показывает все текущие настройки.

---

## Эпик E-4: Детектор текстовых баянов

> **Приоритет: после реализации E-1–E-3.** Текстовые посты — отдельный контент-тип, логика детекции отличается от изображений.

### US-4.1 — Лексический детектор текстовых баянов
> **As an** admin posting text in АК,  
> **I want** the bot to warn me if the same (or near-identical) text was already posted,  
> **so that** we don't repost verbatim copy-pastes.

**Scope:** тексты ≥ 20 символов. Поиск по базе ОК и АК.  
**Алгоритм:** нормализация (lowercase, strip пунктуации) → MinHash / Levenshtein distance с настраиваемым порогом.

**Acceptance Criteria:**
- [ ] Бот проверяет каждый текстовый пост в АК длиной ≥ 20 символов.
- [ ] Если найден лексически похожий текст в ОК или АК — реплай с ссылками (аналогично US-1.1).
- [ ] Если похожих нет — бот молчит.
- [ ] Все новые тексты из ОК и АК сохраняются в БД (text + normalized_hash + chat_id + message_id).
- [ ] Порог похожести настраивается командой `/set_text_threshold N`.
- [ ] Минимальная длина текста для проверки настраивается командой `/set_text_min_len N`.

---

### US-4.2 — Смысловой детектор текстовых баянов *(отложено)*
> **As an** admin,  
> **I want** the bot to catch semantic duplicates — the same idea expressed differently,  
> **so that** we avoid reposting paraphrased content.

**Приоритет: после US-4.1.** Требует embedding-модели (локальной или API).  
**Алгоритм:** текст → embedding вектор → cosine similarity по векторной БД (например, sqlite-vec или pgvector).

**Acceptance Criteria:**
- [ ] *(Уточняется после реализации US-4.1 и выбора embedding-модели.)*

---

## Эпик E-5: Онбординг и мультиворкспейс

> **Архитектурный фундамент**: закладывается с первой итерации. Все данные и конфиг хранятся per-workspace. Онбординг через личку бота.

### US-5.1 — Создание workspace через личку
> **As a** channel owner,  
> **I want** to register my АК and ОК by chatting with the bot privately,  
> **so that** I can set up the bot without any manual intervention from the bot developer.

**Acceptance Criteria:**
- [ ] `/start` в личке создаёт черновик workspace для этого `user_id` и возвращает пошаговую инструкцию.
- [ ] После `/set_ak` в группе и `/set_ok @channel` в личке — workspace переходит в статус `active`.
- [ ] Бот подтверждает активацию и показывает текущий конфиг (`/config`).
- [ ] Если бот не добавлен в ОК как администратор — предупреждает, но workspace сохраняет.
- [ ] Один `user_id` может создать несколько workspace (несколько пар АК→ОК).

---

### US-5.2 — Изоляция данных между workspace
> **When** the bot serves multiple workspaces,  
> **I want** each workspace to have completely isolated data and config,  
> **so that** admins of one channel never see or affect another channel's data.

**Acceptance Criteria:**
- [ ] Поиск баянов (изображения, тексты) — только по записям своего workspace.
- [ ] Голоса, кнопки, конфиг — per-workspace, не глобальные.
- [ ] Команды конфигурации в АК применяются только к workspace этого АК.
- [ ] Схема БД содержит `workspace_id` во всех таблицах с данными.

---

### US-5.4 — Передача workspace другому владельцу *(отложено)*
> **As a** workspace owner,  
> **I want** to transfer ownership of my workspace to another user,  
> **so that** the bot keeps working if I hand off the channel to someone else.

**Приоритет: после реализации US-5.1–5.3.** Требует решения вопроса верификации нового владельца.

**Acceptance Criteria:**
- [ ] *(Уточняется после реализации базового онбординга.)*

---

### US-5.3 — Управление своими workspace *(личный кабинет)*
> **As a** workspace owner,  
> **I want** to see and manage all my registered workspaces from the bot's private chat,  
> **so that** I can update settings or deactivate a workspace without contacting support.

**Acceptance Criteria:**
- [ ] `/my_workspaces` в личке — список всех workspace владельца со статусами.
- [ ] Можно деактивировать workspace командой `/delete_workspace <id>`.
- [ ] После деактивации бот перестаёт реагировать в этих чатах.

---

## Технический долг (из BACKLOG.md, без US)

Эти задачи не имеют пользовательской ценности напрямую, но блокируют или деградируют функционал:

- **TD-1** Race condition с `img_to_search` → `tempfile`
- **TD-2** Бот не сохраняет новые фото в БД (покрывается US-1.2)
- **TD-3** Соединение с БД — singleton в `bot_data`
- **TD-4** Токен в Docker layer history → убрать `ARG`
- **TD-5** Хардкод `chat_id = 1242081849` (покрывается US-3.1)
- **TD-6** Синхронный SQLite → `aiosqlite` / `asyncio.to_thread`
- **TD-7** Разделение `hamming_db.py` на модули
