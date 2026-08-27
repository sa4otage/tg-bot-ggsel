import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
import ggsel
import poller
from config import CODE_TIMEOUT, SPAM_LIMIT, SPAM_WINDOW

_SPAM_WINDOW_MIN = SPAM_WINDOW // 60
from keyboards import (
    back_kb,
    cancel_code_kb,
    cancel_kb,
    delete_email_kb,
    main_menu_kb,
    my_emails_kb,
    select_email_for_code_kb,
)
from states import UserStates

router = Router()
logger = logging.getLogger(__name__)

INSTRUCTION_TEXT = (
    "📖 <b>Инструкция по использованию бота</b>\n\n"
    "1️⃣ Перейди в раздел <b>«Мои почты»</b> и добавь почту полученную при покупке\n(Например: <code>gta5@outlook.com</code>)\n\n"
    "2️⃣ Нажми <b>«Запросить код»</b> и выбери необходимую почту которую ты добавил ранее\n\n"
    "3️⃣ Введи номер своего заказа GGsel (указан в письме об оплате)\n\n"
    "4️⃣ Запроси код в лаунчере для входа в игру (Например: EA, Rockstar Games)\n\n"
    "5️⃣ Бот автоматически поймает письмо и отправит тебе код\n\n"
    "⚠️ <b>Ограничения:</b>\n"
    f"• Максимум {SPAM_LIMIT} запроса на одну почту за {SPAM_WINDOW // 60} минут\n"
    f"• Ожидание кода — {CODE_TIMEOUT} секунд"
)


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    logger.info(f"START from user_id={message.from_user.id} @{message.from_user.username} {message.from_user.first_name}")
    await message.answer(
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        "Я помогу получить код подтверждения из почты Rockstar Games.\n\n"
        "Выбери действие:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


# ── Главное меню ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "instruction")
async def cb_instruction(call: CallbackQuery):
    await call.message.edit_text(
        INSTRUCTION_TEXT,
        reply_markup=back_kb("main_menu"),
        parse_mode="HTML",
    )


# ── Мои почты ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "my_emails")
async def cb_my_emails(call: CallbackQuery):
    mailboxes = await db.get_user_emails_with_service(call.from_user.id)

    if not mailboxes:
        text = "📭 <b>Мои почты</b>\n\nУ тебя ещё нет добавленных почт. Добавь первую!"
    else:
        def _line(i, mb):
            label = f"[{mb['service_name']}] " if mb.get("service_name") else ""
            return f"{i}. {label}<code>{mb['email']}</code>"
        lines = "\n".join(_line(i, mb) for i, mb in enumerate(mailboxes, 1))
        text = f"📬 <b>Мои почты</b>\n\n{lines}"

    await call.message.edit_text(text, reply_markup=my_emails_kb(mailboxes), parse_mode="HTML")


@router.callback_query(F.data == "add_email")
async def cb_add_email(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_email)
    await call.message.edit_text(
        "📧 <b>Добавление почты</b>\n\n"
        "Введи email-адрес (например: <code>gta5@outlook.com</code>):",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )


@router.message(UserStates.waiting_email)
async def msg_add_email(message: Message, state: FSMContext):
    email = message.text.strip().lower()

    if "@" not in email or "." not in email.split("@")[-1]:
        await message.answer("❌ Некорректный email. Попробуй ещё раз:", reply_markup=cancel_kb())
        return

    if await db.user_has_email(message.from_user.id, email):
        await state.clear()
        await message.answer("ℹ️ Эта почта уже есть в твоём списке.", reply_markup=back_kb("my_emails"))
        return

    mailbox = await db.get_shared_mailbox(email)
    if not mailbox:
        await message.answer(
            f"❌ Почта <code>{email}</code> не поддерживается.\n\n"
            "Такого адреса нет в общей базе. Обратись к администратору.",
            reply_markup=cancel_kb(),
            parse_mode="HTML",
        )
        return

    success = await db.add_user_email(message.from_user.id, email)
    await state.clear()

    if success:
        await message.answer(
            f"✅ Почта <code>{email}</code> добавлена!\n\n"
            "Теперь можешь запрашивать с неё коды.",
            reply_markup=back_kb("my_emails"),
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Ошибка при добавлении. Попробуй позже.", reply_markup=back_kb("my_emails"))


@router.callback_query(F.data == "delete_email_menu")
async def cb_delete_email_menu(call: CallbackQuery):
    mailboxes = await db.get_user_emails_with_service(call.from_user.id)

    if not mailboxes:
        await call.answer("У тебя нет добавленных почт", show_alert=True)
        return

    await call.message.edit_text(
        "🗑 <b>Удаление почты</b>\n\nВыбери почту для удаления:",
        reply_markup=delete_email_kb(mailboxes),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("delete_email:"))
async def cb_delete_email(call: CallbackQuery):
    email = call.data.split(":", 1)[1]
    await db.delete_user_email(call.from_user.id, email)
    await call.answer(f"✅ Почта {email} удалена")
    await cb_my_emails(call)


# ── Запрос кода ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "request_code")
async def cb_request_code(call: CallbackQuery):
    mailboxes = await db.get_user_emails_with_service(call.from_user.id)

    if not mailboxes:
        await call.message.edit_text(
            "📭 У тебя нет добавленных почт.\n\n"
            "Сначала добавь почту в разделе «Мои почты».",
            reply_markup=my_emails_kb([]),
            parse_mode="HTML",
        )
        return

    await call.message.edit_text(
        "📬 <b>Запросить код</b>\n\nВыбери почту:",
        reply_markup=select_email_for_code_kb(mailboxes),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("get_code:"))
async def cb_get_code(call: CallbackQuery, state: FSMContext):
    email = call.data.split(":", 1)[1]

    # Проверяем что почта есть в базе
    mailbox = await db.get_shared_mailbox(email)
    if not mailbox:
        await call.answer("❌ Почта недоступна. Обратись к администратору.", show_alert=True)
        return

    await state.set_state(UserStates.waiting_order_number)
    await state.update_data(email=email)
    await call.message.edit_text(
        f"📧 <b>Почта:</b> <code>{email}</code>\n\n"
        "🧾 Введи номер своего заказа GGsel (указан в письме об оплате):",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )


_ORDER_ERROR_TEXTS = {
    "not_found": "❌ Заказ с таким номером не найден. Проверь номер и попробуй ещё раз.",
    "not_paid": "❌ Этот заказ ещё не оплачен или отменён.",
    "api_error": "⚠️ Не удалось проверить заказ (сбой на стороне GGsel). Попробуй через минуту.",
}


@router.message(UserStates.waiting_order_number)
async def msg_order_number(message: Message, state: FSMContext):
    data = await state.get_data()
    email = data.get("email")
    user_id = message.from_user.id
    order_number = message.text.strip()

    mailbox = await db.get_shared_mailbox(email) if email else None
    if not email or not mailbox:
        await state.clear()
        await message.answer("❌ Что-то пошло не так, начни заново.", reply_markup=back_kb("main_menu"))
        return

    checking_msg = await message.answer("🔎 Проверяю заказ...")

    result = await ggsel.verify_order(order_number)
    if not result["ok"]:
        text = _ORDER_ERROR_TEXTS.get(result["reason"], "❌ Не удалось проверить заказ.")
        logger.warning(
            f"[order_check] user_id={user_id} email={email} order={order_number} "
            f"reason={result['reason']}"
        )
        await checking_msg.edit_text(text, reply_markup=cancel_kb())
        return

    bind_result = await db.bind_order_to_user(order_number, user_id)
    if bind_result == "limit_reached":
        await checking_msg.edit_text(
            "❌ Этим номером заказа уже пользуются 2 других Telegram-аккаунта — "
            "лимит достигнут. Обратись к администратору, если это ошибка.",
            reply_markup=cancel_kb(),
        )
        return

    await state.clear()

    # Антиспам
    count = await db.count_recent_requests(user_id, email, SPAM_WINDOW)
    if count >= SPAM_LIMIT:
        await db.log_request(user_id, message.from_user.username, email, "spam")
        await checking_msg.edit_text(
            f"⚠️ Лимит исчерпан!\nМаксимум {SPAM_LIMIT} запроса на одну почту за {_SPAM_WINDOW_MIN} минут.",
            reply_markup=back_kb("main_menu"),
        )
        return

    # Проверяем не занята ли почта другим пользователем
    existing = await db.get_pendings_by_email(email)
    if any(p["user_id"] != user_id for p in existing):
        await checking_msg.edit_text(
            "⏳ Эта почта сейчас занята — другой пользователь уже ожидает код.\n"
            "Попробуй через минуту.",
            reply_markup=back_kb("main_menu"),
        )
        return

    # Логируем запрос
    await db.log_request(user_id, message.from_user.username, email, "pending")

    # Отправляем сообщение ожидания
    msg = await checking_msg.edit_text(
        f"📧 <b>Почта:</b> <code>{email}</code>\n\n"
        "🎮 Запросите код в лаунчере\n\n"
        f"⏳ Ожидаю код... [0/{CODE_TIMEOUT} сек]",
        parse_mode="HTML",
        reply_markup=cancel_code_kb(email),
    )

    await db.create_pending(user_id, email, message.chat.id, msg.message_id, 0)

    from bot import bot
    await poller.start_timer(bot, user_id, email, message.chat.id, msg.message_id)


@router.callback_query(F.data.startswith("cancel_code:"))
async def cb_cancel_code(call: CallbackQuery):
    email = call.data.split(":", 1)[1]
    user_id = call.from_user.id

    poller.cancel_timer(user_id, email)
    await db.delete_pending(user_id, email)

    await call.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu_kb(),
        parse_mode="HTML",
    )
