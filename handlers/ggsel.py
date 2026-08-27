"""
Клиент GGsel Seller API -- используется для проверки номера заказа перед
выдачей кода из почты.

Официальная документация: https://seller.ggsel.com/docs/en

  1) POST /api_sellers/api/apilogin               -- получить токен
  2) GET  /api_sellers/api/purchase/info/{invoice} -- инфо о заказе по номеру
"""

import hashlib
import logging
import time
from datetime import datetime

import aiohttp

from config import GGSEL_SELLER_ID, GGSEL_API_KEY

logger = logging.getLogger(__name__)

API_BASE = "https://seller.ggsel.com/api_sellers/api"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Состояния счёта (invoice_state), которые считаем "оплачено":
# 1-создан, 2-отменён, 3-оплачен, 4-выполнен, 5-возвращён
_PAID_STATES = (3, 4)

_token_cache: dict = {"token": None, "valid_thru": 0.0}


def _sign(api_key: str, timestamp: str) -> str:
    return hashlib.sha256(f"{api_key}{timestamp}".encode()).hexdigest()


async def _get_token() -> str | None:
    now = time.time()
    if _token_cache["token"] and _token_cache["valid_thru"] - now > 120:
        return _token_cache["token"]

    if not GGSEL_SELLER_ID or not GGSEL_API_KEY:
        logger.error("[ggsel] GGSEL_SELLER_ID / GGSEL_API_KEY не заданы в .env")
        return None

    timestamp = str(int(now))
    payload = {
        "seller_id": int(GGSEL_SELLER_ID),
        "timestamp": timestamp,
        "sign": _sign(GGSEL_API_KEY, timestamp),
    }

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.post(
                f"{API_BASE}/apilogin",
                json=payload,
                headers={"Accept": "application/json"},
            ) as resp:
                data = await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[ggsel] apilogin error: {e}")
        return None

    if data.get("retval") != 0 or not data.get("token"):
        logger.error(f"[ggsel] apilogin failed: {data}")
        return None

    _token_cache["token"] = data["token"]
    try:
        valid_thru = datetime.fromisoformat(data["valid_thru"].replace("Z", "+00:00"))
        _token_cache["valid_thru"] = valid_thru.timestamp()
    except Exception:
        _token_cache["valid_thru"] = now + 3600

    logger.info("[ggsel] получен новый токен")
    return _token_cache["token"]


async def get_purchase_raw(invoice_id: str) -> dict | None:
    """Сырой ответ API по номеру заказа. None -- ошибка сети/авторизации."""
    token = await _get_token()
    if not token:
        return None

    invoice_id = str(invoice_id).strip()
    url = f"{API_BASE}/purchase/info/{invoice_id}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.get(
                url,
                params={"token": token},
                headers={"Accept": "application/json", "locale": "ru"},
            ) as resp:
                if resp.status == 404:
                    return {"_not_found": True}
                return await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[ggsel] purchase/info error for invoice={invoice_id}: {e}")
        return None


async def verify_order(invoice_id: str) -> dict:
    """
    Проверяет, что заказ существует и оплачен (без сверки конкретного товара).

    Возвращает {"ok": bool, "reason": str, "raw": dict|None}, reason:
      ok        -- заказ найден и оплачен
      api_error -- сбой сети/авторизации на стороне GGsel
      not_found -- заказ с таким номером не найден
      not_paid  -- заказ найден, но не в статусе "оплачен/выполнен"
    """
    raw = await get_purchase_raw(invoice_id)
    if raw is None:
        return {"ok": False, "reason": "api_error", "raw": None}
    if raw.get("_not_found") or raw.get("retval") != 0:
        return {"ok": False, "reason": "not_found", "raw": raw}

    content = raw.get("content") or {}
    invoice_state = content.get("invoice_state")
    if invoice_state not in _PAID_STATES:
        return {"ok": False, "reason": "not_paid", "raw": raw}

    return {"ok": True, "reason": "ok", "raw": raw}
