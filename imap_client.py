import asyncio
import email as email_lib
import imaplib
import logging
import re

from config import IMAP_EMAIL, IMAP_PASSWORD

logger = logging.getLogger(__name__)

IMAP_HOSTS = {
    'yandex.ru':  ('imap.yandex.ru',  993),
    'ya.ru':      ('imap.yandex.ru',  993),
    'gmail.com':  ('imap.gmail.com',  993),
    'mail.ru':    ('imap.mail.ru',    993),
    'inbox.ru':   ('imap.mail.ru',    993),
    'bk.ru':      ('imap.mail.ru',    993),
    'list.ru':    ('imap.mail.ru',    993),
}


def _get_host():
    domain = IMAP_EMAIL.split('@')[-1].lower()
    return IMAP_HOSTS[domain]


def _connect() -> imaplib.IMAP4_SSL:
    host, port = _get_host()
    mail = imaplib.IMAP4_SSL(host, port, timeout=15)
    mail.login(IMAP_EMAIL, IMAP_PASSWORD)
    mail.select("INBOX")
    return mail


def _extract_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                try:
                    body += part.get_payload(decode=True).decode(errors="ignore")
                except Exception:
                    pass
    else:
        try:
            body = msg.get_payload(decode=True).decode(errors="ignore")
        except Exception:
            pass
    return body


def _extract_code(text: str) -> str | None:
    clean = re.sub(r"<[^>]+>", " ", text)
    matches = re.findall(r"(?<!\d)(\d{6})(?!\d)", clean)
    return matches[0] if matches else None


def _extract_recipient_email(text: str) -> str | None:
    clean = re.sub(r"<[^>]+>", " ", text)
    matches = re.findall(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", clean)
    for m in matches:
        m_lower = m.lower()
        if m_lower != IMAP_EMAIL.lower() and "rockstar" not in m_lower:
            return m_lower
    return None


def get_last_uid_sync() -> int:
    try:
        mail = _connect()
        _, data = mail.uid("search", None, "ALL")
        mail.logout()
        if not data[0]:
            return 0
        uids = data[0].split()
        return int(uids[-1]) if uids else 0
    except Exception as e:
        print(f"[IMAP] get_last_uid error: {e}")
        return 0


def fetch_new_codes_sync(last_uid: int) -> list[dict]:
    """Возвращает список {'email': ..., 'code': ...} для новых писем."""
    results = []
    try:
        mail = _connect()

        if last_uid > 0:
            criteria = f'UID {last_uid + 1}:*'
        else:
            criteria = 'ALL'

        _, data = mail.uid("search", None, criteria)
        logger.info(f"[IMAP] search criteria='{criteria}' raw={data}")

        if not data[0]:
            mail.logout()
            return results

        uids = [u for u in data[0].split() if int(u) > last_uid]
        logger.info(f"[IMAP] new uids: {uids}")
        if not uids:
            mail.logout()
            return results

        for uid in uids:
            _, msg_data = mail.uid("fetch", uid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email_lib.message_from_bytes(msg_data[0][1])
            body = _extract_body(msg)
            code = _extract_code(body)
            recipient = _extract_recipient_email(body)

            # Fallback: тело не содержит email — ищем в заголовках письма
            # Outlook при пересылке добавляет разные заголовки с оригинальным адресом
            if not recipient:
                fallback_headers = [
                    "X-Original-To",
                    "X-Forwarded-To",
                    "X-MS-Exchange-Inbox-Rules-Loop",
                    "Resent-To",
                    "Delivered-To",
                    "From",
                ]
                for header_name in fallback_headers:
                    header_val = msg.get(header_name, "")
                    if not header_val:
                        continue
                    emails_found = re.findall(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", header_val)
                    for m in emails_found:
                        m_lower = m.lower()
                        if (m_lower != IMAP_EMAIL.lower()
                                and "rockstar" not in m_lower
                                and "yandex" not in m_lower):
                            recipient = m_lower
                            logger.info(f"[IMAP] uid={uid} recipient from header '{header_name}': {recipient}")
                            break
                    if recipient:
                        break

            logger.info(f"[IMAP] uid={uid} code={code} recipient={recipient}")
            if code and not recipient:
                debug_headers = {h: msg.get(h) for h in ["From", "To", "Delivered-To", "X-Original-To", "X-Forwarded-To", "X-MS-Exchange-Inbox-Rules-Loop", "Resent-To"] if msg.get(h)}
                logger.warning(f"[IMAP] uid={uid} code found but NO recipient. Headers: {debug_headers}")
            if code and recipient:
                results.append({"email": recipient, "code": code, "uid": int(uid)})

        mail.logout()
    except Exception as e:
        logger.error(f"[IMAP] fetch_new_codes error: {e}")
    return results


async def get_last_uid() -> int:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_last_uid_sync)


async def fetch_new_codes(last_uid: int) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch_new_codes_sync, last_uid)
