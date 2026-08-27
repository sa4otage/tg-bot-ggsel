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
async def msg_mb_service_name(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    email = data.get("email")
    service_name = message.text.strip()
    await state.clear()

    if not email:
        await message.answer("❌ Что-то пошло не так, начни заново.", reply_markup=back_kb("admin_mailboxes"))
        return

    success = await db.add_shared_mailbox(email=email, password="", service_name=service_name)

    if success:
        await message.answer(
            f"✅ Почта <code>{email}</code> добавлена с подписью <b>[{service_name}]</b>!",
            parse_mode="HTML",
            reply_markup=back_kb("admin_mailboxes"),
        )
    else:
        await message.answer(
            "❌ Ошибка — такая почта уже существует или произошёл сбой.",
            reply_markup=back_kb("admin_mailboxes"),
        )


# ── Пользователи ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_users")
async def cb_admin_users(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    users = await db.get_all_users_with_emails()

    if not users:
        await call.message.edit_text("👥 Пользователей нет.", reply_markup=back_kb("admin_menu"))
        return

    user_map: dict[int, list[str]] = defaultdict(list)
    usernames: dict[int, str] = {}
    for u in users:
        user_map[u["user_id"]].append(u["email"])
        if u.get("username"):
            usernames[u["user_id"]] = u["username"]

    lines = []
    for i, (uid, emails) in enumerate(list(user_map.items())[:20], 1):
        uname = f"@{usernames[uid]}" if uid in usernames else f"ID:{uid}"
        lines.append(f"{i}. {uname}")
        for e in emails:
            lines.append(f"   └ <code>{e}</code>")

    extra = f"\n...и ещё {len(user_map) - 20}" if len(user_map) > 20 else ""
    await call.message.edit_text(
        "👥 <b>Пользователи</b>\n\n" + "\n".join(lines) + extra,
        reply_markup=back_kb("admin_menu"),
        parse_mode="HTML",
    )


# ── Статистика ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    s = await db.get_stats()
    total = s["total_requests"] or 1
    success_pct = s["success_requests"] * 100 // total
    timeout_pct = s["timeout_requests"] * 100 // total

    await call.message.edit_text(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Уникальных пользователей: <b>{s['total_users']}</b>\n"
        f"📬 Активных общих почт: <b>{s['active_mailboxes']}</b>\n\n"
        f"📈 Всего запросов: <b>{s['total_requests']}</b>\n"
        f"✅ Успешно: <b>{s['success_requests']}</b> ({success_pct}%)\n"
        f"⏱ Таймаут: <b>{s['timeout_requests']}</b> ({timeout_pct}%)",
        reply_markup=back_kb("admin_menu"),
        parse_mode="HTML",
    )


# ── Логи ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_logs")
async def cb_admin_logs(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    logs = await db.get_recent_logs(15)

    if not logs:
        await call.message.edit_text("📋 Логов нет.", reply_markup=back_kb("admin_menu"))
        return

    icons = {"success": "✅", "timeout": "⏱", "spam": "🚫", "pending": "⏳"}
    lines = []
    for log in logs:
        icon = icons.get(log["status"], "❓")
        code_str = f" → <code>{log['code']}</code>" if log.get("code") else ""
        lines.append(f"{icon} <code>{log['email'][:25]}</code>{code_str}")
        lines.append(f"   {log['created_at'][:16]}")

    await call.message.edit_text(
        "📋 <b>Последние 15 запросов</b>\n\n" + "\n".join(lines),
        reply_markup=back_kb("admin_menu"),
        parse_mode="HTML",
    )
