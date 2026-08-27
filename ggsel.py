"""
Клиент GGsel/Digiseller Seller API — используется для проверки номера
заказа перед выдачей кода из почты.

GGsel технически работает на инфраструктуре Digiseller, поэтому продавцу
доступен обычный Digiseller Seller API:
  1) POST /api/apilogin              -- получить токен (живёт ~сутки)
  2) GET  /api/purchases/info/{id}   -- инфо о заказе по номеру

Официальная документация: https://my.digiseller.com/inside/api.asp
(нужен логин в личном кабинете продавца).

ВАЖНО: названия полей в ответе /purchases/info не задокументированы
на 100% публично (в разных источниках встречаются id_d / product_id /
id_goods для ID товара). Перед боевым запуском прогоните
`python check_ggsel.py <номер_реального_заказа>` и убедитесь, что
_extract_product_id ниже находит правильное поле -- при необходимости
допишите имя поля в список кандидатов.
"""

import hashlib
import logging
import time
from datetime import datetime

import aiohttp

from config import GGSEL_SELLER_ID, GGSEL_API_KEY

logger = logging.getLogger(__name__)

API_BASE = "https://api.digiseller.ru/api"
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Кандидаты названий поля с ID товара в ответе purchases/info.
_PRODUCT_ID_FIELDS = ("id_d", "product_id", "id_goods", "goods_id", "productId")

_token_cache: dict = {"token": None, "valid_thru": 0.0}


def _sign(api_key: str, timestamp: int) -> str:
    return hashlib.sha256(f"{api_key}{timestamp}".encode()).hexdigest()


async def _get_token() -> str | None:
    now = time.time()
    if _token_cache["token"] and _token_cache["valid_thru"] - now > 120:
        return _token_cache["token"]

    if not GGSEL_SELLER_ID or not GGSEL_API_KEY:
        logger.error("[ggsel] GGSEL_SELLER_ID / GGSEL_API_KEY не заданы в .env")
        return None

    timestamp = int(now)
    payload = {
        "seller_id": int(GGSEL_SELLER_ID),
        "timestamp": timestamp,
        "sign": _sign(GGSEL_API_KEY, timestamp),
    }

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.post(f"{API_BASE}/apilogin", json=payload) as resp:
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
        _token_cache["valid_thru"] = now + 3600  # запасной запас, если формат другой

    logger.info("[ggsel] получен новый токен")
    return _token_cache["token"]


async def get_purchase_raw(invoice_id: str) -> dict | None:
    """Сырой ответ API по номеру заказа. None -- ошибка сети/авторизации."""
    token = await _get_token()
    if not token:
        return None

    invoice_id = str(invoice_id).strip()
    url = f"{API_BASE}/purchases/info/{invoice_id}"

    try:
        async with aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT) as session:
            async with session.get(url, params={"token": token}) as resp:
                if resp.status == 404:
                    return {"_not_found": True}
                return await resp.json(content_type=None)
    except Exception as e:
        logger.error(f"[ggsel] purchases/info error for invoice={invoice_id}: {e}")
        return None


def _extract_product_id(raw: dict) -> str | None:
    for key in _PRODUCT_ID_FIELDS:
        if raw.get(key) is not None:
            return str(raw[key])
    return None


async def verify_order(invoice_id: str, expected_product_id: str | None) -> dict:
    """
    Проверяет, что заказ существует и относится к нужному товару.

    Возвращает {"ok": bool, "reason": str, "raw": dict|None}, где reason:
      ok                    -- всё сошлось
      no_config             -- для этой почты не привязан product_id (админ не настроил)
      api_error             -- сбой сети/авторизации на стороне GGsel
      not_found             -- заказ с таким номером не найден
      wrong_product         -- заказ найден, но товар не совпадает
      unknown_product_field -- заказ найден, но не удалось понять, в каком поле ID товара
                               (нужно поправить _PRODUCT_ID_FIELDS)
    """
    if not expected_product_id:
        return {"ok": False, "reason": "no_config", "raw": None}

    raw = await get_purchase_raw(invoice_id)
    if raw is None:
        return {"ok": False, "reason": "api_error", "raw": None}
    if raw.get("_not_found") or raw.get("retval") not in (0, None):
        return {"ok": False, "reason": "not_found", "raw": raw}

    found_product_id = _extract_product_id(raw)
    if found_product_id is None:
        logger.warning(f"[ggsel] не найдено поле с ID товара в ответе: {raw}")
        return {"ok": False, "reason": "unknown_product_field", "raw": raw}

    if found_product_id != str(expected_product_id):
        return {"ok": False, "reason": "wrong_product", "raw": raw}

    return {"ok": True, "reason": "ok", "raw": raw}
