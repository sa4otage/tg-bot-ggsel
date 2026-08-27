from collections import defaultdict

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import ADMIN_IDS
from keyboards import (
    admin_mailboxes_kb,
    admin_mb_actions_kb,
    admin_menu_kb,
    back_kb,
)
from states import AdminStates

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── /admin ────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        _stats_text(stats),
        reply_markup=admin_menu_kb(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    stats = await db.get_stats()
    await call.message.edit_text(
        _stats_text(stats),
        reply_markup=admin_menu_kb(),
        parse_mode="HTML",
    )


def _stats_text(stats: dict) -> str:
    return (
        "🔧 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: <b>{stats['total_users']}</b>\n"
        f"📬 Активных почт: <b>{stats['active_mailboxes']}</b>\n"
        f"✅ Успешных запросов: <b>{stats['success_requests']}</b>\n"
        f"📊 Всего запросов: <b>{stats['total_requests']}</b>"
    )


# ── Управление почтами ────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_mailboxes")
async def cb_admin_mailboxes(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    mailboxes = await db.get_all_shared_mailboxes()
    await call.message.edit_text(
        "📬 <b>Управление почтами</b>\n\nВыбери почту для управления:",
        reply_markup=admin_mailboxes_kb(mailboxes),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_mb:"))
async def cb_admin_mb_detail(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    mb_id = int(call.data.split(":")[1])
    mailboxes = await db.get_all_shared_mailboxes()
    mb = next((m for m in mailboxes if m["id"] == mb_id), None)
    if not mb:
        await call.answer("Почта не найдена", show_alert=True)
        return

    status = "✅ Активна" if mb["is_active"] else "❌ Неактивна"
    service_line = f"🎮 Сервис: <b>{mb['service_name']}</b>\n" if mb.get("service_name") else ""
    await call.message.edit_text(
        f"📬 <b>{mb['email']}</b>\n\n"
        f"{service_line}"
        f"Статус: {status}",
        reply_markup=admin_mb_actions_kb(mb_id, mb["is_active"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin_toggle_mb:"))
async def cb_admin_toggle(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    _, mb_id, new_state = call.data.split(":")
    await db.toggle_mailbox(int(mb_id), int(new_state))
    await call.answer("✅ Статус изменён")
    await cb_admin_mb_detail(call)


@router.callback_query(F.data.startswith("admin_delete_mb:"))
async def cb_admin_delete(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    mb_id = int(call.data.split(":")[1])
    await db.delete_shared_mailbox(mb_id)
    await call.answer("✅ Почта удалена")
    await cb_admin_mailboxes(call)


# ── Добавление почты (FSM) ────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_mb")
async def cb_admin_add_mb(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_mb_email)
    await call.message.edit_text(
        "➕ <b>Добавление почты</b>\n\nВведи Outlook-адрес:",
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_mb_email)
async def msg_mb_email(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    email = message.text.strip().lower()
    await state.update_data(email=email)
    await state.set_state(AdminStates.waiting_mb_service_name)
    await message.answer(
        "🎮 <b>Название сервиса</b>\n\n"
        "Введи, как подписать эту почту для покупателя, например: <code>Rockstar Games</code> "
        "или <code>EA</code>. Покупатель увидит эту подпись рядом с почтой в «Мои почты».",
        parse_mode="HTML",
    )


@router.message(AdminStates.waiting_mb_service_name)
async
