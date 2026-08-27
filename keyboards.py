from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔑 Запросить код", callback_data="request_code")
    b.button(text="📬 Мои почты", callback_data="my_emails")
    b.button(text="📖 Инструкция", callback_data="instruction")
    b.adjust(1)
    return b.as_markup()


def my_emails_kb(emails: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for email in emails:
        b.button(text=f"📧 {email}", callback_data=f"get_code:{email}")
    b.button(text="➕ Добавить почту", callback_data="add_email")
    if emails:
        b.button(text="🗑 Удалить почту", callback_data="delete_email_menu")
    b.button(text="◀️ Назад", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def select_email_for_code_kb(emails: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for email in emails:
        b.button(text=f"📧 {email}", callback_data=f"get_code:{email}")
    b.button(text="◀️ Назад", callback_data="main_menu")
    b.adjust(1)
    return b.as_markup()


def delete_email_kb(emails: list[str]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for email in emails:
        b.button(text=f"❌ {email}", callback_data=f"delete_email:{email}")
    b.button(text="◀️ Назад", callback_data="my_emails")
    b.adjust(1)
    return b.as_markup()


def cancel_code_kb(email: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отменить", callback_data=f"cancel_code:{email}")
    return b.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="❌ Отмена", callback_data="main_menu")
    return b.as_markup()


def back_kb(target: str = "main_menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data=target)
    return b.as_markup()


# ── Admin ─────────────────────────────────────────────────────────────────────

def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📬 Управление почтами", callback_data="admin_mailboxes")
    b.button(text="👥 Пользователи", callback_data="admin_users")
    b.button(text="📊 Статистика", callback_data="admin_stats")
    b.button(text="📋 Логи", callback_data="admin_logs")
    b.adjust(1)
    return b.as_markup()


def admin_mailboxes_kb(mailboxes: list[dict]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for mb in mailboxes:
        icon = "✅" if mb["is_active"] else "❌"
        b.button(text=f"{icon} {mb['email']}", callback_data=f"admin_mb:{mb['id']}")
    b.button(text="➕ Добавить почту", callback_data="admin_add_mb")
    b.button(text="◀️ Назад", callback_data="admin_menu")
    b.adjust(1)
    return b.as_markup()


def admin_mb_actions_kb(mb_id: int, is_active: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    toggle_text = "🔴 Деактивировать" if is_active else "🟢 Активировать"
    b.button(text=toggle_text, callback_data=f"admin_toggle_mb:{mb_id}:{1 - is_active}")
    b.button(text="🗑 Удалить", callback_data=f"admin_delete_mb:{mb_id}")
    b.button(text="◀️ Назад", callback_data="admin_mailboxes")
    b.adjust(1)
    return b.as_markup()
