"""
Утилита для проверки интеграции с GGsel/Digiseller API до запуска бота
в бою.

Использование:
    python check_ggsel.py <номер_заказа>

Печатает сырой JSON-ответ /api/purchases/info по этому заказу.
Посмотрите, в каком поле приходит ID товара (обычно id_d, но может
называться иначе) -- и, если он отличается от списка в ggsel.py
(_PRODUCT_ID_FIELDS), допишите туда правильное имя поля.
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

    found = ggsel._extract_product_id(raw)
    if found:
        print(f"\n✅ Поле с ID товара найдено: {found}")
    else:
        print(
            "\n⚠️ Не нашёл ID товара ни в одном из ожидаемых полей "
            f"{ggsel._PRODUCT_ID_FIELDS}. Посмотри в JSON выше, как называется "
            "нужное поле, и добавь его имя в ggsel._PRODUCT_ID_FIELDS."
        )


if __name__ == "__main__":
    asyncio.run(main())
