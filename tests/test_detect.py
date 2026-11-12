"""Проверки SentiGuard: что находит и что НЕ должен находить. Запуск: pytest -q tests"""
import pytest
from fastapi.testclient import TestClient

from main import app

c = TestClient(app)


def luhn_make(prefix: str, length: int = 16) -> str:
    base = prefix + "0" * (length - len(prefix) - 1)
    for d in range(10):
        n = base + str(d)
        s = 0
        for i, x in enumerate(int(ch) for ch in reversed(n)):
            if i % 2:
                x *= 2
                x -= 9 if x > 9 else 0
            s += x
        if s % 10 == 0:
            return n


def found(text):
    r = c.post("/analyze", json={"text": text})
    assert r.status_code == 200
    return [(e["type"], e["text"]) for e in r.json()]


def types(text):
    return {t for t, _ in found(text)}


POSITIVE = [
    ("Отправь документ Ивану Иванову", "PER", "Ивану Иванову"),
    ("Договор подписал Петров Сергей Николаевич вчера", "PER", "Петров Сергей Николаевич"),
    ("звонила мария кузнецова насчёт заказа", "PER", "мария кузнецова"),
    ("Мой телефон +7 (999) 123-45-67", "PHONE_NUMBER", "+7 (999) 123-45-67"),
    ("звоните 8 999 123 45 67 после обеда", "PHONE_NUMBER", "8 999 123 45 67"),
    ("тел. 89991234567", "PHONE_NUMBER", "89991234567"),
    ("whatsapp 9991234567", "PHONE_NUMBER", "9991234567"),
    ("Паспорт 4510 123456 выдан ОВД", "RU_PASSPORT", "4510 123456"),
    ("серия 45 10 № 123456", "RU_PASSPORT", "45 10 № 123456"),
    ("СНИЛС 112-233-445 95", "RU_SNILS", "112-233-445 95"),
    ("снилс 11223344595", "RU_SNILS", "11223344595"),
    ("ИНН 500100732259", "RU_INN", "500100732259"),
    ("ИНН организации 7707083893", "RU_INN", "7707083893"),
    ("ОГРН 1027700132195", "RU_OGRN", "1027700132195"),
    ("почта ivan.petrov@mail.ru", "EMAIL_ADDRESS", "ivan.petrov@mail.ru"),
    ("сервер 192.168.10.25 не отвечает", "IP_ADDRESS", "192.168.10.25"),
    ("адрес 2001:db8::ff00:42:8329", "IP_ADDRESS", "2001:db8::ff00:42:8329"),
    ("MAC 00:1A:2B:3C:4D:5E", "MAC_ADDRESS", "00:1A:2B:3C:4D:5E"),
    ("живу: г. Москва, ул. Ленина, д. 5, кв. 12", "ADDRESS", None),
    ("доставка на проспект Мира 15 кв 3", "ADDRESS", None),
    ("полис ОМС 7700 1234 5678 9012", "RU_OMS", "7700 1234 5678 9012"),
    ("водительские права 77 АВ 123456", "RU_DRIVER_LICENSE", "77 АВ 123456"),
    ("загранпаспорт 75 1234567", "RU_INT_PASSPORT", "75 1234567"),
    ("свидетельство о рождении II-МЮ 654321", "RU_BIRTH_CERT", "II-МЮ 654321"),
    ("военный билет АК 1234567", "RU_MILITARY_ID", "АК 1234567"),
    ("р/с 40817810099910004312", "RU_BANK_ACCOUNT", "40817810099910004312"),
    ("машина А123ВС77 стоит во дворе", "RU_CAR_PLATE", "А123ВС77"),
    ("дата рождения 12.03.1985", "BIRTH_DATE", "12.03.1985"),
    ("пиши в телеграм @ivan_petrov", "USERNAME", "@ivan_petrov"),
    ("пароль: Qwerty12345", "SECRET", "Qwerty12345"),
    ("ключ sk-proj-abcdefghijklmnopqrstuvwxyz123456", "SECRET", None),
    ("CVV 123", "CARD_CVV", "123"),
    ("IBAN DE89370400440532013000", "IBAN_CODE", "DE89370400440532013000"),
    ("Contact John Smith at john@example.com", "PER", "John Smith"),
    ("сайт https://example.com/profile/42", "URL", None),
    ("карта 4111 1111 1111 1112", "CREDIT_CARD", "4111 1111 1111 1112"),  # рядом «карта»: ловим и без Луна
    ("ИНН 7707083893, КПП 770701001", "RU_KPP", "770701001"),
    ("скинь на карту 4276 3800 1234 5675 сбер", "CREDIT_CARD", "4276 3800 1234 5675"),
    ("Call me at +1 (415) 555-0132", "PHONE_NUMBER", "+1 (415) 555-0132"),
    ("Меня зовут Смирнова Ольга Петровна", "PER", "Смирнова Ольга Петровна"),
    ("125009, г. Москва, ул. Тверская, д. 7, кв. 15", "ADDRESS", "125009, г. Москва, ул. Тверская, д. 7, кв. 15"),
]


@pytest.mark.parametrize("text,typ,val", POSITIVE)
def test_positive(text, typ, val):
    res = found(text)
    assert any(t == typ and (val is None or v == val) for t, v in res), res


def test_cards():
    visa, mir = "4111 1111 1111 1111", luhn_make("2200", 16)
    mir = " ".join(mir[i:i + 4] for i in range(0, 16, 4))
    for num in (visa, mir):
        assert ("CREDIT_CARD", num) in found(f"карта {num}")


NEGATIVE = [
    # Начало слова — не сокращение улицы (12.11.2026: «Проверка…» уходила модели как [АДРЕС_1]).
    ("Проверка пульта. Запомни число 47.", "ADDRESS"),
    ("Проверка пульта 12.11 19:45:02. Столица Франции?", "ADDRESS"),
    ("Пришли прайс на 25 позиций", "ADDRESS"),
    ("Прочитай главу 5 и ответь", "ADDRESS"),
    ("Шаг 3: перепроверь расчёт 15", "ADDRESS"),
    ("Плюс 5 баллов за ответ", "ADDRESS"),
    ("Переведи текст 2 на английский", "ADDRESS"),
    ("Глава 5, страница 47", "ADDRESS"),
    ("ИНН 1234567890", "RU_INN"),                # неверная контрольная сумма
    ("СНИЛС 123-456-789 00", "RU_SNILS"),       # неверная контрольная сумма
    ("номер заказа 4111 1111 1111 1112", "CREDIT_CARD"),  # не проходит Луна и нет слова «карта»
    ("в 2023 году продали 1500 штук за 45000 рублей", "RU_PASSPORT"),
    ("заказ номер 1234567", "RU_MILITARY_ID"),
    ("Сегодня Хорошая Погода И Мы Идём Гулять", "PER"),
    ("купил хлеб и молоко", "PER"),
    ("Заказ № 4510123456 отгружен", "RU_PASSPORT"),
    ("Артикул 1234567890123, КПП не нужен", "PHONE_NUMBER"),
    ("в 2023 году рост 12%, встреча в 14:30", "DATE_TIME"),
]


ADRESA = [
    ("ул. Ленина, д. 5, кв. 12", "ул. Ленина, д. 5, кв. 12"),
    ("доставка: пр. Мира, 15, кв. 4", "пр. Мира, 15, кв. 4"),
    ("живу на Тверской улице, дом 7", "Тверской улице, дом 7"),
    ("офис на проспекте Победы, д. 3", "проспекте Победы, д. 3"),
    ("Садовый переулок, 9", "Садовый переулок, 9"),
]


@pytest.mark.parametrize("text,val", ADRESA)
def test_adres(text, val):
    """Адрес с улицей и домом находится и в падеже («на Тверской улице»)."""
    assert ("ADDRESS", val) in found(text), found(text)


def test_spisok_tipov_bez_mest_i_kompanij():
    """Чат AI-Tech-API просит искать всё, кроме LOC и ORG: страна и компания остаются в тексте."""
    vse = [e["type"] for e in c.get("/entities").json()]
    nuzhno = [t for t in vse if t not in ("LOC", "ORG")]
    text = "Столица Франции? Передай Иван Петров из Сбербанк: звонить на +7 999 123-45-67"
    r = c.post("/anonymize", json={"text": text, "entities": nuzhno, "mode": "tag"}).json()
    assert "Франции" in r["text"] and "Сбербанк" in r["text"], r["text"]
    assert "Иван Петров" not in r["text"] and "+7 999" not in r["text"], r["text"]
    assert {i["type"] for i in r["items"]} <= set(nuzhno)
    # без списка — по-прежнему всё, в том числе места
    vse_r = c.post("/anonymize", json={"text": text, "mode": "tag"}).json()
    assert "Франции" not in vse_r["text"], vse_r["text"]


@pytest.mark.parametrize("text,typ", NEGATIVE)
def test_negative(text, typ):
    assert typ not in types(text), found(text)


def test_positions_with_extra_spaces():
    text = "Привет.\n\n   Звонил   Ивану   Иванову    вчера,   тел  +7 999 123-45-67"
    for e in c.post("/analyze", json={"text": text}).json():
        assert text[e["start"]:e["end"]] == e["text"]
    assert ("PER", "Ивану   Иванову") in found(text)


def test_anonymize_roundtrip():
    text = "Иван Петров, тел. +7 999 123-45-67, почта ivan@mail.ru. Иван Петров придёт завтра."
    r = c.post("/anonymize", json={"text": text}).json()
    assert "+7 999" not in r["text"] and "ivan@mail.ru" not in r["text"] and "Петров" not in r["text"]
    assert r["text"].count("[ФИО_1]") == 2
    back = c.post("/deanonymize", json={"text": r["text"], "items": r["items"]}).json()["text"]
    assert back == text


def test_entities_list():
    ents = {e["type"] for e in c.get("/entities").json()}
    for t in ("PER", "RU_PASSPORT", "RU_SNILS", "RU_INN", "PHONE_NUMBER", "IP_ADDRESS", "EMAIL_ADDRESS"):
        assert t in ents
