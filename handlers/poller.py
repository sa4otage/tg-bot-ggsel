import asyncio
import logging

from aiogram import Bot

import database as db
import imap_client
from config import CODE_TIMEOUT, POLL_INTERVAL
from keyboards import back_kb, cancel_code_kb

logger = logging.getLogger(__name__)

# (user_id, email) -> asyncio.Task
_timer_tasks: dict[tuple, asyncio.Task] = {}


async def start_global_poller(bot: Bot):
    """Единственный IMAP-поллер для всех пользователей."""
    last_uid = await imap_client.get_last_uid()
    logger.info(f"[poller] started, last_uid={last_uid}")
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            new_codes = await imap_client.fetch_new_codes(last_uid)
            for item in new_codes:
                if item["uid"] > last_uid:
                    last_uid = item["uid"]
                pendings = await db.get_pendings_by_email(item["email"])
                for pending in pendings:
                    await _deliver_code(bot, pending, item["code"])
        except Exception as e:
            logger.error(f"[poller] error: {e}")


async def _deliver_code(bot: Bot, pending: dict, code: str):
    user_id = pending["user_id"]
    email = pending["email"]

    await db.delete_pending(user_id, email)
    await db.log_request(user_id, None, email, "success", code)

    task_key = (user_id, email)
    if task_key in _timer_tasks:
        _timer_tasks.pop(task_key).cancel()

    try:
        await bot.edit_message_text(
            f"📧 <b>Почта:</b> <code>{email}</code>\n\n"
            f"✅ <b>Ваш код:</b>  <code>{code}</code>",
            chat_id=pending["chat_id"],
            message_id=pending["message_id"],
            parse_mode="HTML",
            reply_markup=back_kb("main_menu"),
        )
    except Exception as e:
        logger.error(f"[poller] deliver error user_id={user_id}: {e}")


def cancel_timer(user_id: int, email: str):
    task_key = (user_id, email)
    if task_key in _timer_tasks:
        _timer_tasks.pop(task_key).cancel()


async def start_timer(bot: Bot, user_id: int, email: str, chat_id: int, message_id: int):
    task = asyncio.create_task(
        _timer_loop(bot, user_id, email, chat_id, message_id)
    )
    _timer_tasks[(user_id, email)] = task


async def _timer_loop(bot: Bot, user_id: int, email: str, chat_id: int, message_id: int):
    elapsed = 0
    while elapsed < CODE_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        if not await db.get_pending(user_id, email):
            return

        try:
            await bot.edit_message_text(
                f"📧 <b>Почта:</b> <code>{email}</code>\n\n"
                "🎮 Теперь запросите код в лаунчере\n\n"
                f"⏳ Ожидаю код... [{elapsed}/{CODE_TIMEOUT} сек]",
                chat_id=chat_id,
                message_id=message_id,
                parse_mode="HTML",
                reply_markup=cancel_code_kb(email),
            )
        except Exception:
            pass

    # Таймаут
    _timer_tasks.pop((user_id, email), None)
    await db.delete_pending(user_id, email)
    await db.log_request(user_id, None, email, "timeout")
    try:
        await bot.edit_message_text(
            f"📧 <b>Почта:</b> <code>{email}</code>\n\n"
            f"❌ Код не пришёл за {CODE_TIMEOUT} секунд.\n\n"
            "Попробуй ещё раз.",
            chat_id=chat_id,
            message_id=message_id,
            parse_mode="HTML",
            reply_markup=back_kb("main_menu"),
        )
    except Exception as e:
        logger.error(f"[timer] timeout edit error user_id={user_id}: {e}")
