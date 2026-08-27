import aiosqlite
from datetime import datetime, timedelta
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shared_mailboxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                imap_email TEXT,
                imap_password TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Миграция: добавляем поля если таблица уже существует
        for col, typ in [
            ("imap_email", "TEXT"),
            ("imap_password", "TEXT"),
            ("service_name", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE shared_mailboxes ADD COLUMN {col} {typ}")
                await db.commit()
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                added_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, email)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pending_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                last_uid INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                email TEXT NOT NULL,
                code TEXT,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(invoice_id, user_id)
            )
        """)
        await db.commit()


# ── Shared mailboxes ─────────────────────────────────────────────────────────

async def get_shared_mailbox(email: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shared_mailboxes WHERE email = ? AND is_active = 1", (email,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_shared_mailboxes() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM shared_mailboxes ORDER BY created_at DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_shared_mailbox(
    email: str, password: str,
    imap_email: str | None = None, imap_password: str | None = None,
    service_name: str | None = None,
) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO shared_mailboxes (email, password, imap_email, imap_password, service_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (email, password, imap_email, imap_password, service_name),
            )
            await db.commit()
        return True
    except Exception:
        return False


async def delete_shared_mailbox(mailbox_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM shared_mailboxes WHERE id = ?", (mailbox_id,))
        await db.commit()


async def toggle_mailbox(mailbox_id: int, is_active: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE shared_mailboxes SET is_active = ? WHERE id = ?",
            (is_active, mailbox_id),
        )
        await db.commit()


# ── User emails ───────────────────────────────────────────────────────────────

async def get_user_emails(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_emails WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_user_emails_with_service(user_id: int) -> list[dict]:
    """То же самое, но с меткой сервиса (service_name) из shared_mailboxes."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT ue.email AS email, sm.service_name AS service_name
            FROM user_emails ue
            LEFT JOIN shared_mailboxes sm ON sm.email = ue.email
            WHERE ue.user_id = ?
            ORDER BY ue.added_at DESC
            """,
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def add_user_email(user_id: int, email: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO user_emails (user_id, email) VALUES (?, ?)",
                (user_id, email),
            )
            await db.commit()
        return True
    except Exception:
        return False


async def delete_user_email(user_id: int, email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM user_emails WHERE user_id = ? AND email = ?",
            (user_id, email),
        )
        await db.commit()


async def user_has_email(user_id: int, email: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM user_emails WHERE user_id = ? AND email = ?",
            (user_id, email),
        ) as cur:
            return await cur.fetchone() is not None


# ── Pending codes ─────────────────────────────────────────────────────────────

async def create_pending(
    user_id: int, email: str, chat_id: int, message_id: int, last_uid: int = 0
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_codes WHERE user_id = ? AND email = ?",
            (user_id, email),
        )
        await db.execute(
            "INSERT INTO pending_codes (user_id, email, chat_id, message_id, last_uid) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, email, chat_id, message_id, last_uid),
        )
        await db.commit()


async def get_pending(user_id: int, email: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pending_codes WHERE user_id = ? AND email = ?",
            (user_id, email),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_pendings_by_email(email: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM pending_codes WHERE email = ?", (email,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def delete_pending(user_id: int, email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM pending_codes WHERE user_id = ? AND email = ?",
            (user_id, email),
        )
        await db.commit()


async def get_all_pendings() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pending_codes") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def clear_all_pendings():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM pending_codes")
        await db.commit()


# ── Antispam & logs ───────────────────────────────────────────────────────────

async def count_recent_requests(user_id: int, email: str, window_seconds: int = 1800) -> int:
    cutoff = (datetime.utcnow() - timedelta(seconds=window_seconds)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM request_logs "
            "WHERE user_id = ? AND email = ? AND created_at > ? AND status = 'pending'",
            (user_id, email, cutoff),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def log_request(
    user_id: int,
    username: str | None,
    email: str,
    status: str,
    code: str | None = None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO request_logs (user_id, username, email, code, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, username, email, code, status),
        )
        await db.commit()


# ── Admin ─────────────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_emails"
        ) as c:
            total_users = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM shared_mailboxes WHERE is_active = 1"
        ) as c:
            active_mailboxes = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM request_logs WHERE status = 'success'"
        ) as c:
            success_requests = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM request_logs WHERE status = 'timeout'"
        ) as c:
            timeout_requests = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM request_logs") as c:
            total_requests = (await c.fetchone())[0]
    return {
        "total_users": total_users,
        "active_mailboxes": active_mailboxes,
        "success_requests": success_requests,
        "timeout_requests": timeout_requests,
        "total_requests": total_requests,
    }


async def get_all_users_with_emails() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT ue.user_id, ue.email,
                   (SELECT rl.username FROM request_logs rl
                    WHERE rl.user_id = ue.user_id AND rl.username IS NOT NULL
                    LIMIT 1) as username
            FROM user_emails ue
            ORDER BY ue.user_id
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_recent_logs(limit: int = 15) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM request_logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── GGsel order verification ──────────────────────────────────────────────────
async def has_bound_order(user_id: int) -> bool:
    """Есть ли у пользователя хотя бы одна привязка номера заказа."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM order_bindings WHERE user_id = ? LIMIT 1", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None
            
async def bind_order_to_user(invoice_id: str, user_id: int) -> str:
    """
    Привязывает номер заказа к телеграм-аккаунту. Максимум 2 разных
    пользователя на один номер заказа (например, покупатель + друг).

    Возвращает "ok" (привязка есть/только что создана) или "limit_reached"
    (уже привязаны 2 других пользователя).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM order_bindings WHERE invoice_id = ? AND user_id = ?",
            (invoice_id, user_id),
        ) as cur:
            if await cur.fetchone():
                return "ok"  # уже привязан этот пользователь

        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM order_bindings WHERE invoice_id = ?",
            (invoice_id,),
        ) as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0

        if count >= 2:
            return "limit_reached"

        await db.execute(
            "INSERT INTO order_bindings (invoice_id, user_id) VALUES (?, ?)",
            (invoice_id, user_id),
        )
        await db.commit()
        return "ok"
