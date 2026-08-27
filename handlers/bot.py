import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, TelegramObject

from config import BOT_TOKEN, TELEGRAM_PROXY
import database as db
import poller
from handlers import admin, user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class AutoAnswerCallbackMiddleware:
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except Exception:
                pass
        return result


# Прокси нужен только если сервер бота стоит там, где Telegram Bot API
# заблокирован/нестабилен (например, РФ). Задаётся через TELEGRAM_PROXY в .env,
# формат: socks5://host:port или socks5://user:pass@host:port.
# Пусто -- прямое подключение без прокси.
session = AiohttpSession(proxy=TELEGRAM_PROXY) if TELEGRAM_PROXY else AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)


async def _cleanup_stale_pendings():
    pendings = await db.get_all_pendings()
    if not pendings:
        return
    logger.info(f"Cleaning up {len(pendings)} stale pending requests")
    for p in pendings:
        try:
            await bot.send_message(
                p["chat_id"],
                f"⚠️ Бот перезапустился, запрос кода для <code>{p['email']}</code> отменён.\n\n"
                "Пожалуйста, запроси код заново.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    await db.clear_all_pendings()


async def main():
    await db.init_db()
    logger.info("Database initialized")
    logger.info(
        "Telegram proxy: %s",
        TELEGRAM_PROXY if TELEGRAM_PROXY else "не используется (прямое подключение)",
    )

    await _cleanup_stale_pendings()

    dp = Dispatcher(storage=MemoryStorage())
    dp.callback_query.middleware(AutoAnswerCallbackMiddleware())
    dp.include_router(admin.router)
    dp.include_router(user.router)

    poller_task = asyncio.create_task(poller.start_global_poller(bot))
    logger.info("Bot started")

    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        # Важно для чистого рестарта: если процесс не отпустит соединение
        # с getUpdates до старта нового -- Telegram вернёт
        # TelegramConflictError ("terminated by other getUpdates request"),
        # и оба инстанса начнут долбиться друг в друга бесконечными
        # реконнектами. Поэтому всегда явно закрываем сессию и поллер.
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Bot stopped, session closed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Interrupted")
