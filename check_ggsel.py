"""
Утилита для проверки интеграции с GGsel API до запуска бота в бою.

Использование:
    python check_ggsel.py <номер_заказа>
"""
import asyncio
import json
import sys

import ggsel


async def main():
    if len(sys.argv) < 2:
        print("Использование: python check_ggsel.py <номер_заказа>")
        return

    invoice_id = sys.argv[1]
    raw = await ggsel.get_purchase_raw(invoice_id)

    if raw is None:
        print("Не удалось получить ответ -- проверь GGSEL_SELLER_ID / GGSEL_API_KEY в .env и сеть.")
        return

    print(json.dumps(raw, ensure_ascii=False, indent=2))

    content = raw.get("content") or {}
    item_id = content.get("item_id")
    invoice_state = content.get("invoice_state")

    print(f"\nitem_id (ID товара): {item_id}")
    print(f"invoice_state (статус): {invoice_state} (3=оплачен, 4=выполнен -- считаются оплаченными)")


if __name__ == "__main__":
    asyncio.run(main())
