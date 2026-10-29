"""Российские и прочие шаблонные маркеры с проверкой контрольных сумм и контекста.

Каждый детектор возвращает кандидатов (start, end, type, score). Оценка растёт, если
рядом (в окне перед находкой) стоит слово-подсказка: «паспорт», «СНИЛС», «ИНН» и т.п.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass
class Hit:
    start: int
    end: int
    type: str
    score: float
    source: str = "regex"
    normal: Optional[str] = None
    case: Optional[str] = None
    extra: dict = field(default_factory=dict)


def digits(s: str) -> str:
    return re.sub(r"\D", "", s)


# ---------- контрольные суммы ----------

def inn_ok(s: str) -> bool:
    d = [int(c) for c in digits(s)]
    if len(d) == 10:
        k = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(k, d)) % 11 % 10 == d[9]
    if len(d) == 12:
        k1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        k2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        return (sum(a * b for a, b in zip(k1, d)) % 11 % 10 == d[10]
                and sum(a * b for a, b in zip(k2, d)) % 11 % 10 == d[11])
    return False


def snils_ok(s: str) -> bool:
    d = digits(s)
    if len(d) != 11:
        return False
    if int(d[:9]) <= 1001998:  # номера до 001-001-998 контрольной суммы не имеют
        return True
    t = sum(int(c) * (9 - i) for i, c in enumerate(d[:9]))
    if t > 101:
        t %= 101
    cs = 0 if t in (100, 101) else t
    return cs == int(d[9:])


def ogrn_ok(s: str) -> bool:
    d = digits(s)
    if len(d) == 13:
        return int(d[:12]) % 11 % 10 == int(d[12])
    if len(d) == 15:
        return int(d[:14]) % 13 % 10 == int(d[14])
    return False


def luhn_ok(s: str) -> bool:
    d = [int(c) for c in digits(s)][::-1]
    if len(d) < 12:
        return False
    tot = 0
    for i, x in enumerate(d):
        if i % 2:
            x *= 2
            if x > 9:
                x -= 9
        tot += x
    return tot % 10 == 0


def _ip_ok(s: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def not_same_digit(s: str) -> bool:
    d = digits(s)
    return len(set(d)) > 1


# ---------- описание детекторов ----------

@dataclass
class Rule:
    type: str
    pattern: str
    base: float                    # оценка без подсказки рядом
    ctx: Optional[str] = None      # регулярка слов-подсказок (ищется перед находкой)
    with_ctx: float = 0.9          # оценка при подсказке
    validate: Optional[Callable[[str], bool]] = None
    flags: int = re.IGNORECASE
    group: int = 0                 # какая группа регулярки является значением
    ctx_required: bool = False     # без подсказки не засчитывать

    def __post_init__(self):
        self.rx = re.compile(self.pattern, self.flags)
        self.crx = re.compile(self.ctx, re.IGNORECASE) if self.ctx else None


B = r"(?<![\w\d])"   # левая граница: не буква/цифра
E = r"(?![\w\d])"    # правая граница
PLATE_L = "АВЕКМНОРСТУХABEKMHOPCTYX"

RULES: List[Rule] = [
    # Телефоны РФ/СНГ (+7, 8, 7). Международные ловит ещё и Presidio (libphonenumber).
    Rule("PHONE_NUMBER",
         B + r"(?:\+7|8|7)[\s\-\u00a0]*\(?\s*\d{3}\s*\)?[\s\-\u00a0]*\d{3}[\s\-\u00a0]*\d{2}[\s\-\u00a0]*\d{2}" + E,
         0.75, r"тел|phone|моб|сот|whatsapp|вотсап|ватсап|telegram|телеграм|звон|номер", 0.95),
    Rule("PHONE_NUMBER", B + r"9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}" + E,
         0.35, r"тел|phone|моб|сот|whatsapp|вотсап|ватсап|звон|номер", 0.85),
    # СНИЛС: 123-456-789 01 или 11 цифр подряд, с контрольной суммой
    Rule("RU_SNILS", B + r"\d{3}[\-\s]?\d{3}[\-\s]?\d{3}[\-\s]?\d{2}" + E,
         0.6, r"снилс|страхов|пенсион|сниллс|snils", 0.95, validate=snils_ok),
    # ИНН физлица (12) и организации (10) с контрольной суммой
    Rule("RU_INN", B + r"\d{12}" + E, 0.65, r"инн|inn|налогопл", 0.95, validate=inn_ok),
    Rule("RU_INN", B + r"\d{10}" + E, 0.5, r"инн|inn|налогопл", 0.95, validate=inn_ok),
    # ОГРН (13) / ОГРНИП (15)
    Rule("RU_OGRN", B + r"\d{13}" + E, 0.5, r"огрн|ogrn|регистрац", 0.95, validate=ogrn_ok),
    Rule("RU_OGRN", B + r"\d{15}" + E, 0.45, r"огрнип|огрн|ogrn", 0.95, validate=ogrn_ok),
    # Паспорт РФ: серия 4 цифры + номер 6 цифр
    Rule("RU_PASSPORT", B + r"\d{2}\s?\d{2}\s*(?:№|N|No\.?|номер)?\s*\d{6}" + E,
         0.3, r"паспорт|серия|серии|passport|удостоверяющ|выдан", 0.95, validate=not_same_digit),
    # КПП: 9 цифр, только рядом со словом КПП (иначе это любое число)
    Rule("RU_KPP", B + r"\d{4}[0-9A-Z]{2}\d{3}" + E, 0.2, r"кпп|kpp", 0.9, ctx_required=True),
    # Загранпаспорт: 2 цифры + 7 цифр
    Rule("RU_INT_PASSPORT", B + r"\d{2}\s?№?\s?\d{7}" + E,
         0.2, r"загран|заграничн|international passport|passport", 0.9, ctx_required=True),
    # Водительское удостоверение: 2 цифры + 2 цифры/буквы + 6 цифр
    Rule("RU_DRIVER_LICENSE", B + r"\d{2}\s?(?:\d{2}|[" + PLATE_L + r"]{2})\s?№?\s?\d{6}" + E,
         0.3, r"водит|в/у|\bву\b|права|driver", 0.95, ctx_required=True),
    # Полис ОМС единого образца: 16 цифр
    Rule("RU_OMS", B + r"\d{4}\s?\d{4}\s?\d{4}\s?\d{4}" + E,
         0.3, r"омс|полис|медицинск|oms", 0.9, ctx_required=True),
    # Свидетельство о рождении: II-АБ 123456
    Rule("RU_BIRTH_CERT", B + r"[IVXLС1]{1,4}\s?-\s?[А-ЯЁ]{2}\s?№?\s?\d{6}" + E,
         0.7, r"свидетельств|рождени", 0.95, flags=0),
    # Военный билет: АБ 1234567
    Rule("RU_MILITARY_ID", B + r"[А-ЯЁ]{2}\s?№?\s?\d{7}" + E,
         0.3, r"военн|билет", 0.9, flags=0, ctx_required=True),
    # Лицевой/расчётный счёт физлица: 20 цифр, 408 (счета физлиц) и 423 (вклады)
    Rule("RU_BANK_ACCOUNT", B + r"(?:408|423)\d{2}[\s.]?\d{3}[\s.]?\d[\s.]?\d{4}[\s.]?\d{7}" + E,
         0.75, r"сч[её]т|р/с|л/с|account|реквизит", 0.95),
    Rule("RU_BANK_ACCOUNT", B + r"\d{20}" + E,
         0.4, r"сч[её]т|р/с|л/с|к/с|account|реквизит", 0.85, ctx_required=True),
    # Банковская карта (в т.ч. «Мир» 2200-2204, которую Presidio не знает), проверка Луна
    Rule("CREDIT_CARD", B + r"\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?:[\s\-]?\d{1,3})?" + E,
         0.8, r"карт|card|visa|master|мир", 0.95, validate=luhn_ok),
    # Рядом со словом «карта» берём 16 цифр и без проверки Луна (опечатка или выдуманный номер тоже утечка)
    Rule("CREDIT_CARD", B + r"\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}" + E,
         0.2, r"карт|card|visa|master|сбер|тинькоф|т-банк|альфа|втб", 0.7, ctx_required=True),
    # CVV/CVC только рядом с подсказкой
    Rule("CARD_CVV", r"(?:cvv|cvc|cvv2|cvc2|код\s+безопасности)\W{0,3}(\d{3,4})" + E, 0.85, group=1),
    # IMEI: 15 цифр, Луна, только с подсказкой
    Rule("IMEI", B + r"\d{15}" + E, 0.2, r"imei|имей", 0.9, validate=luhn_ok, ctx_required=True),
    # Госномер автомобиля
    Rule("RU_CAR_PLATE", B + r"[" + PLATE_L + r"]\s?\d{3}\s?[" + PLATE_L + r"]{2}\s?\d{2,3}" + E,
         0.6, r"госномер|номер\s+авто|авто|машин|гос\.?\s*номер|г/н|грз", 0.9, flags=0),
    # Даты рождения; просто даты - низкая оценка
    Rule("BIRTH_DATE",
         B + r"(?:\d{1,2}[./\-]\d{1,2}[./\-](?:19|20)\d{2}|\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(?:19|20)\d{2})" + E,
         0.3, r"рожд|родил|д\.\s?р|\bдр\b|birth|born|dob|возраст", 0.9),
    # IP v4/v6 с проверкой библиотекой ipaddress (Presidio пропускает сокращённые IPv6)
    Rule("IP_ADDRESS", r"(?<![\w.:])(?:\d{1,3}\.){3}\d{1,3}(?![\w.]|\.\d)", 0.8, validate=lambda s: _ip_ok(s)),
    Rule("IP_ADDRESS", r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])", 0.8,
         validate=lambda s: _ip_ok(s) and s.count(":") >= 2 and len(s) >= 6),
    # MAC-адрес
    Rule("MAC_ADDRESS", B + r"(?:[0-9A-F]{2}[:\-]){5}[0-9A-F]{2}" + E, 0.8),
    # Ник в соцсетях/Telegram (не почта)
    Rule("USERNAME", r"(?<![\w@.])@[A-Za-z][A-Za-z0-9_]{3,31}" + E, 0.55,
         r"telegram|телеграм|тг|tg|инст|insta|vk|вк|ник|пиши", 0.8, flags=0),
    # Секреты: ключи API, токены, пароли
    Rule("SECRET", r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}", 0.95, flags=0),
    Rule("SECRET", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 0.95, flags=0),
    Rule("SECRET", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}", 0.95, flags=0),
    Rule("SECRET", r"\bglpat-[A-Za-z0-9_\-]{20}\b", 0.95, flags=0),
    Rule("SECRET", r"\bxox[abprs]-[A-Za-z0-9\-]{10,}", 0.95, flags=0),
    Rule("SECRET", r"\bAIza[0-9A-Za-z_\-]{35}\b", 0.95, flags=0),
    Rule("SECRET", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b", 0.95, flags=0),  # токен Telegram-бота
    Rule("SECRET", r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}", 0.9, flags=0),  # JWT
    Rule("SECRET", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----", 0.99, flags=0),
    Rule("SECRET", r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:@/]+:([^\s@/]+)@", 0.95, group=1),
    Rule("SECRET",
         r"(?:парол[ьяе]|password|passwd|pwd|pass|пароль\s+от\s+\S+|token|токен|api[_\-\s]?key|secret|секрет)\s*(?:[:=]|—|-|это|is)\s*[\"'«]?([^\s\"'»,;]{4,})",
         0.85, group=1),
]


def context_before(text: str, start: int, width: int = 60) -> str:
    return text[max(0, start - width):start]


def context_around(text: str, start: int, end: int, width: int = 60) -> str:
    return text[max(0, start - width):start] + " " + text[end:end + 25]


def find_rules(text: str) -> List[Hit]:
    out: List[Hit] = []
    for r in RULES:
        for m in r.rx.finditer(text):
            s, e = m.span(r.group)
            if s < 0 or s == e:
                continue
            val = text[s:e]
            if r.validate and not r.validate(val):
                continue
            has_ctx = bool(r.crx and r.crx.search(context_around(text, s, e)))
            if r.ctx_required and not has_ctx:
                continue
            score = r.with_ctx if has_ctx else r.base
            out.append(Hit(s, e, r.type, score, "regex", normal=val))
    return out
