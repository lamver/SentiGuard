"""Движок SentiGuard: Natasha (ФИО, места, организации, адреса) + Presidio (почта, карты, IP, URL, IBAN,
международные телефоны и др.) + российские шаблоны с контрольными суммами (ru.py).

Все позиции (start/end) считаются по ИСХОДНОМУ тексту.
"""
import re
from typing import Iterable, List, Optional

from natasha import (Doc, MorphVocab, NewsEmbedding, NewsMorphTagger, NewsNERTagger, Segmenter,
                     AddrExtractor)
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import PhoneRecognizer

from .ru import Hit, find_rules

# ---------- справочник маркеров ----------
# тип -> (описание по-русски, откуда берётся)
ENTITY_INFO = {
    # Natasha
    "PER": ("ФИО, имя или фамилия человека (в любом падеже, с нормальной формой)", "natasha"),
    "LOC": ("Географическое название: город, страна, регион", "natasha"),
    "ORG": ("Организация", "natasha"),
    "ADDRESS": ("Почтовый адрес: улица, дом, квартира", "natasha+regex"),
    # Presidio
    "EMAIL_ADDRESS": ("Электронная почта", "presidio"),
    "PHONE_NUMBER": ("Телефон (РФ/СНГ и международные)", "regex+presidio"),
    "CREDIT_CARD": ("Номер банковской карты, в т.ч. «Мир» (проверка Луна)", "regex+presidio"),
    "IP_ADDRESS": ("IP-адрес v4/v6", "regex+presidio"),
    "URL": ("Ссылка/домен", "presidio"),
    "IBAN_CODE": ("Международный номер счёта IBAN", "presidio"),
    "CRYPTO": ("Адрес криптокошелька (Bitcoin)", "presidio"),
    "DATE_TIME": ("Дата/время (только английский текст, через spaCy)", "presidio"),
    "NRP": ("Национальность, религия, политические взгляды (английский текст)", "presidio"),
    "MEDICAL_LICENSE": ("Медицинская лицензия США", "presidio"),
    "US_SSN": ("Номер соцстрахования США", "presidio"),
    "US_PASSPORT": ("Паспорт США", "presidio"),
    "US_DRIVER_LICENSE": ("Водительские права США", "presidio"),
    "US_ITIN": ("ИНН налогоплательщика США", "presidio"),
    "US_BANK_NUMBER": ("Номер счёта США", "presidio"),
    "UK_NHS": ("Номер NHS Великобритании", "presidio"),
    "UK_NINO": ("Национальный страховой номер Великобритании", "presidio"),
    "ES_NIF": ("NIF Испании", "presidio"),
    "ES_NIE": ("NIE Испании", "presidio"),
    "IT_FISCAL_CODE": ("Налоговый код Италии", "presidio"),
    "IT_DRIVER_LICENSE": ("Права Италии", "presidio"),
    "IT_VAT_CODE": ("НДС-код Италии", "presidio"),
    "IT_PASSPORT": ("Паспорт Италии", "presidio"),
    "IT_IDENTITY_CARD": ("Удостоверение Италии", "presidio"),
    "PL_PESEL": ("PESEL Польши", "presidio"),
    "SG_NRIC_FIN": ("NRIC/FIN Сингапура", "presidio"),
    "SG_UEN": ("UEN Сингапура", "presidio"),
    "AU_ABN": ("ABN Австралии", "presidio"),
    "AU_ACN": ("ACN Австралии", "presidio"),
    "AU_TFN": ("TFN Австралии", "presidio"),
    "AU_MEDICARE": ("Medicare Австралии", "presidio"),
    "IN_PAN": ("PAN Индии", "presidio"),
    "IN_AADHAAR": ("Aadhaar Индии", "presidio"),
    "IN_VEHICLE_REGISTRATION": ("Госномер Индии", "presidio"),
    "IN_VOTER": ("Удостоверение избирателя Индии", "presidio"),
    "IN_PASSPORT": ("Паспорт Индии", "presidio"),
    "FI_PERSONAL_IDENTITY_CODE": ("Личный код Финляндии", "presidio"),
    # Российские шаблоны (ru.py)
    "RU_PASSPORT": ("Паспорт РФ: серия и номер", "regex"),
    "RU_INT_PASSPORT": ("Загранпаспорт РФ (только рядом со словом «загран»/passport)", "regex"),
    "RU_SNILS": ("СНИЛС (с контрольной суммой)", "regex"),
    "RU_INN": ("ИНН физлица (12) и организации (10), с контрольной суммой", "regex"),
    "RU_KPP": ("КПП организации (рядом со словом «КПП»)", "regex"),
    "RU_OGRN": ("ОГРН / ОГРНИП, с контрольной суммой", "regex"),
    "RU_DRIVER_LICENSE": ("Водительское удостоверение РФ (рядом со словом «права»/«в/у»)", "regex"),
    "RU_OMS": ("Полис ОМС (рядом со словом «полис»/«ОМС»)", "regex"),
    "RU_BIRTH_CERT": ("Свидетельство о рождении", "regex"),
    "RU_MILITARY_ID": ("Военный билет (рядом со словом «военный»)", "regex"),
    "RU_BANK_ACCOUNT": ("Банковский счёт РФ, 20 цифр", "regex"),
    "RU_CAR_PLATE": ("Госномер автомобиля РФ", "regex"),
    "CARD_CVV": ("CVV/CVC карты", "regex"),
    "IMEI": ("IMEI телефона (рядом со словом IMEI)", "regex"),
    "BIRTH_DATE": ("Дата рождения; дата без подсказки идёт с низкой оценкой", "regex"),
    "MAC_ADDRESS": ("MAC-адрес", "regex"),
    "USERNAME": ("Ник вида @name (Telegram, соцсети)", "regex"),
    "SECRET": ("Пароли, токены, ключи API, приватные ключи, пароль в строке подключения", "regex"),
}

# Метки для маскировки
PLACEHOLDER = {
    "PER": "ФИО", "LOC": "МЕСТО", "ORG": "ОРГАНИЗАЦИЯ", "ADDRESS": "АДРЕС", "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "ТЕЛЕФОН", "CREDIT_CARD": "КАРТА", "IP_ADDRESS": "IP", "URL": "ССЫЛКА", "IBAN_CODE": "IBAN",
    "CRYPTO": "КРИПТОКОШЕЛЁК", "RU_PASSPORT": "ПАСПОРТ", "RU_INT_PASSPORT": "ЗАГРАНПАСПОРТ", "RU_SNILS": "СНИЛС",
    "RU_INN": "ИНН", "RU_KPP": "КПП", "RU_OGRN": "ОГРН", "RU_DRIVER_LICENSE": "ВУ", "RU_OMS": "ОМС", "RU_BIRTH_CERT": "СВИДЕТЕЛЬСТВО",
    "RU_MILITARY_ID": "ВОЕННЫЙ_БИЛЕТ", "RU_BANK_ACCOUNT": "СЧЁТ", "RU_CAR_PLATE": "ГОСНОМЕР", "CARD_CVV": "CVV",
    "IMEI": "IMEI", "BIRTH_DATE": "ДАТА", "MAC_ADDRESS": "MAC", "USERNAME": "НИК", "SECRET": "СЕКРЕТ",
    "DATE_TIME": "ДАТА",
}

# Presidio-типы, которые считаем только в латинице (spaCy en на русском тексте даёт мусор)
LATIN_ONLY = {"PERSON", "LOCATION", "NRP", "DATE_TIME", "ORGANIZATION"}
PRESIDIO_MAP = {"PERSON": "PER", "LOCATION": "LOC", "ORGANIZATION": "ORG"}
# Presidio-телефон мы заменяем своим (он ловит «номера» в ИНН/СНИЛС); оставляем лишь явный международный формат
CYR = re.compile(r"[А-Яа-яЁё]")

STREET = (r"(?:ул(?:ица)?|пр(?:оспект|-к?т|осп)?|пер(?:еулок)?|ш(?:оссе)?|б(?:ульва)?р|бул|наб(?:ережная)?|"
          r"пл(?:ощадь)?|пр-д|проезд|тупик|аллея|мкр|микрорайон|квартал|линия|тракт)\.?")
ADDR_RX = re.compile(
    r"(?<![\w])(?:(?:г(?:ород)?\.?\s*[А-ЯЁ][\w\-]+|[А-ЯЁ][\w\-]+\s+обл(?:асть|\.)?|пос(?:ёлок|елок)?\.?\s*[А-ЯЁ][\w\-]+|"
    r"с\.\s*[А-ЯЁ][\w\-]+|д\.\s*[А-ЯЁ][\w\-]+)\s*,\s*)*"
    r"(?:" + STREET + r"\s*[А-ЯЁA-Z0-9][\w\-\. ]{1,40}?|[А-ЯЁ][\w\-]+\s+" + STREET + r")"
    r"\s*,?\s*(?:д(?:ом)?\.?\s*)?\d+[\w/\-]*"
    r"(?:\s*,?\s*(?:к(?:орп(?:ус)?)?|стр(?:оение)?|лит(?:ера)?)\.?\s*\d+\w?)?"
    r"(?:\s*,?\s*(?:кв(?:артира)?|оф(?:ис)?|пом(?:ещение)?)\.?\s*\d+\w?)?",
    re.IGNORECASE)
INDEX_RX = re.compile(r"(?<!\d)\d{6}(?!\d)(?=\s*,\s*(?:г\.|город|[А-ЯЁ][\w\-]+\s+обл|Москва|Санкт))")

PERSON_TAGS = {"Name", "Surn", "Patr"}


class Engine:
    def __init__(self):
        self.segmenter = Segmenter()
        self.morph_vocab = MorphVocab()
        emb = NewsEmbedding()
        self.morph_tagger = NewsMorphTagger(emb)
        self.ner_tagger = NewsNERTagger(emb)
        self.addr_extractor = AddrExtractor(self.morph_vocab)

        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]})
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(languages=["en"])
        # Телефоны: регионы по умолчанию американские/европейские. Добавляем СНГ и соседей.
        registry.remove_recognizer("PhoneRecognizer")
        registry.add_recognizer(PhoneRecognizer(supported_regions=(
            "RU", "KZ", "BY", "UA", "UZ", "KG", "TJ", "AM", "AZ", "GE", "MD", "TR", "US", "GB", "DE", "FR", "IT",
            "ES", "PL", "IL", "AE", "CN", "IN", "TH", "VN", "RS", "CY", "LV", "LT", "EE", "FI")))
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), registry=registry)
        self.presidio_entities = sorted(self.analyzer.get_supported_entities("en"))

    # ----- Natasha -----
    def _is_person_word(self, word: str) -> bool:
        try:
            forms = self.morph_vocab.parse(word)
        except Exception:
            return False
        for f in forms[:3]:
            tags = set(str(f.tag).replace(" ", ",").split(","))
            if tags & PERSON_TAGS:
                return True
        return False

    def _ner(self, text: str) -> List[Hit]:
        doc = Doc(text)
        doc.segment(self.segmenter)
        doc.tag_morph(self.morph_tagger)
        doc.tag_ner(self.ner_tagger)
        out = []
        for span in doc.spans:
            span.normalize(self.morph_vocab)
            case = None
            if span.tokens and span.tokens[0].feats:
                case = span.tokens[0].feats.get("Case")
            out.append(Hit(span.start, span.stop, span.type, 0.85, "natasha", normal=span.normal, case=case))
        return out

    def natasha(self, text: str) -> List[Hit]:
        hits = self._ner(text)
        # Имена с маленькой буквы: делаем заглавной первую букву слова, НЕ меняя длину текста,
        # и принимаем из второго прохода только PER, где есть слово-имя по словарю pymorphy.
        capped = re.sub(r"(?<![\w])([а-яё])", lambda m: m.group(1).upper(), text)
        if capped != text:
            seen = {(h.start, h.end) for h in hits}
            for h in self._ner(capped):
                if h.type != "PER" or (h.start, h.end) in seen:
                    continue
                words = re.findall(r"[А-Яа-яЁё]+", text[h.start:h.end])
                if words and all(self._is_person_word(w.capitalize()) for w in words):
                    h.score = 0.6
                    h.source = "natasha-lower"
                    hits.append(h)
        return hits

    def addresses(self, text: str) -> List[Hit]:
        out = []
        for m in ADDR_RX.finditer(text):
            out.append(Hit(m.start(), m.end(), "ADDRESS", 0.85, "regex", normal=m.group(0)))
        for m in INDEX_RX.finditer(text):
            out.append(Hit(m.start(), m.end(), "ADDRESS", 0.7, "regex", normal=m.group(0)))
        try:
            for m in self.addr_extractor(text):
                parts = m.fact.parts if hasattr(m.fact, "parts") else []
                # одиночный «город Москва» - это LOC, а не адрес; адрес - от двух частей с номером дома/улицей
                kinds = {getattr(p, "type", None) for p in parts}
                if len(parts) >= 2 and kinds & {"улица", "проспект", "переулок", "шоссе", "бульвар", "набережная",
                                                "площадь", "проезд", "дом", "квартира", "микрорайон"}:
                    out.append(Hit(m.start, m.stop, "ADDRESS", 0.8, "natasha-addr", normal=text[m.start:m.stop]))
        except Exception:
            pass
        return out

    # ----- Presidio -----
    def presidio(self, text: str, entities: Optional[Iterable[str]] = None) -> List[Hit]:
        ents = list(entities) if entities else self.presidio_entities
        out = []
        for r in self.analyzer.analyze(text=text, language="en", entities=ents, score_threshold=0.0):
            val = text[r.start:r.end]
            if r.entity_type in LATIN_ONLY and CYR.search(val):
                continue
            # spaCy называет датой любое число («2001», «15»): берём дату, только если в ней есть слово
            if r.entity_type == "DATE_TIME" and not re.search(r"[A-Za-z]", val):
                continue
            # Presidio-телефон без «+», скобок и разделителей - это просто число (КПП, артикул); РФ-номера ловит ru.py
            if r.entity_type == "PHONE_NUMBER" and (val.isdigit() or re.fullmatch(r"\d{3}-\d{2}-\d{4}", val)):
                continue
            if r.entity_type == "PHONE_NUMBER" and val.startswith("+"):
                r.score = max(r.score, 0.75)
            typ = PRESIDIO_MAP.get(r.entity_type, r.entity_type)
            out.append(Hit(r.start, r.end, typ, float(r.score), "presidio", normal=val))
        return out

    # ----- всё вместе -----
    def analyze(self, text: str, entities: Optional[List[str]] = None, score_threshold: float = 0.4) -> List[Hit]:
        want = set(entities) if entities else None
        cand: List[Hit] = []
        cand += self.natasha(text)
        cand += self.addresses(text)
        cand += find_rules(text)
        cand += self.presidio(text)
        cand = [h for h in cand if h.score >= score_threshold and (want is None or h.type in want)]
        return resolve(cand, text)

    def entity_list(self):
        """Только то, что реально работает: наши типы + фактически загруженные распознаватели Presidio."""
        loaded = {PRESIDIO_MAP.get(e, e) for e in self.presidio_entities}
        types = {t: v for t, v in ENTITY_INFO.items() if v[1] != "presidio" or t in loaded}
        for e in loaded:
            types.setdefault(e, (e, "presidio"))
        return [{"type": t, "description": d, "source": s, "placeholder": PLACEHOLDER.get(t, t)}
                for t, (d, s) in sorted(types.items())]


# Приоритет при пересечении: точные документы важнее общих «цифр» и «мест»
PRIORITY = {"SECRET": 10, "RU_PASSPORT": 8, "RU_SNILS": 8, "RU_INN": 7, "RU_OGRN": 7, "CREDIT_CARD": 8,
            "RU_BANK_ACCOUNT": 8, "RU_OMS": 7, "EMAIL_ADDRESS": 9, "URL": 3, "ADDRESS": 6, "PHONE_NUMBER": 6,
            "PER": 5, "IP_ADDRESS": 7, "LOC": 2, "ORG": 2, "DATE_TIME": 1, "BIRTH_DATE": 4}


def resolve(hits: List[Hit], text: str) -> List[Hit]:
    """Убираем пересечения: побеждает более высокая оценка, затем приоритет типа, затем длина."""
    hits = sorted(hits, key=lambda h: (-h.score, -PRIORITY.get(h.type, 5), -(h.end - h.start)))
    taken: List[Hit] = []
    for h in hits:
        if any(h.start < t.end and t.start < h.end for t in taken):
            # адрес поглощает попавшие в него места/организации - уже учтено приоритетом
            continue
        taken.append(h)
    return merge_adjacent(sorted(taken, key=lambda h: h.start), text)


# Соседние куски одного типа склеиваем: «Смирнова» + «Ольга Петровна» -> одно ФИО;
# «125009» + «г. Москва, ул. …» -> один адрес.
GLUE = {"PER": re.compile(r"\s{1,3}"), "ADDRESS": re.compile(r"\s*,?\s*"), "LOC": re.compile(r"\s*,\s*")}


def merge_adjacent(hits: List[Hit], text: str) -> List[Hit]:
    out: List[Hit] = []
    for h in hits:
        p = out[-1] if out else None
        g = GLUE.get(h.type)
        if p and g and p.type == h.type and g.fullmatch(text[p.end:h.start]):
            p.end = h.end
            p.score = max(p.score, h.score)
            p.normal = f"{p.normal or ''} {h.normal or ''}".strip() if h.type == "PER" else text[p.start:p.end]
            continue
        out.append(h)
    return out


def anonymize(text: str, hits: List[Hit], mode: str = "tag"):
    """mode: tag -> [ФИО_1]; mask -> ****; redact -> удалить. Одинаковые значения получают одну метку."""
    counters, seen, items = {}, {}, []
    out, pos = [], 0
    for h in sorted(hits, key=lambda h: h.start):
        val = text[h.start:h.end]
        out.append(text[pos:h.start])
        if mode == "mask":
            rep = "*" * len(val)
        elif mode == "redact":
            rep = ""
        else:
            key = (h.type, (h.normal or val).strip().lower())
            if key not in seen:
                counters[h.type] = counters.get(h.type, 0) + 1
                seen[key] = f"[{PLACEHOLDER.get(h.type, h.type)}_{counters[h.type]}]"
                items.append({"placeholder": seen[key], "type": h.type, "text": val})
            rep = seen[key]
        out.append(rep)
        pos = h.end
    out.append(text[pos:])
    return "".join(out), items


def deanonymize(text: str, items: List[dict]) -> str:
    for it in sorted(items, key=lambda i: -len(i["placeholder"])):
        text = text.replace(it["placeholder"], it["text"])
    return text
