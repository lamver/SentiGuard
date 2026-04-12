import re
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from natasha import (
    Segmenter, MorphVocab, NewsEmbedding, 
    NewsMorphTagger, NewsNERTagger, Doc
)
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider
import yaml

app = FastAPI()

# 1. Загрузка конфига и инициализация движков
with open("languages-config.yml", "r") as f:
    config = yaml.safe_load(f)

segmenter = Segmenter()
morph_vocab = MorphVocab()
emb = NewsEmbedding()
morph_tagger = NewsMorphTagger(emb)
ner_tagger = NewsNERTagger(emb)

provider = NlpEngineProvider(nlp_configuration=config)
nlp_engine = provider.create_engine()
analyzer_en = AnalyzerEngine(nlp_engine=nlp_engine)

# 2. Добавление кастомных регулярных выражений (РФ специфика)
inn_pattern = Pattern(name="inn_pattern", regex=r"\b\d{10}(\d{2})?\b", score=0.5)
inn_recognizer = PatternRecognizer(supported_entity="RU_INN", patterns=[inn_pattern])
analyzer_en.registry.add_recognizer(inn_recognizer)

class Entity(BaseModel):
    text: str
    normal: Optional[str] = None
    case: Optional[str] = None
    start: int
    end: int
    type: str

class AnalysisRequest(BaseModel):
    text: str

@app.post("/analyze", response_model=List[Entity])
async def analyze(request: AnalysisRequest):
    text = request.text
    results = []

    # РЕШЕНИЕ ПРОБЛЕМЫ МАЛЕНЬКИХ БУКВ: 
    # Создаем копию текста, где каждое слово с большой буквы для NER
    capitalized_text = ". ".join([s.strip().capitalize() for s in text.split('.')])
    # Или более мягкий вариант:
    soft_cap_text = ' '.join([w.capitalize() if w.islower() else w for w in text.split()])

    # Natasha (Русский) - используем "нормализованный" текст для поиска имен
    doc = Doc(soft_cap_text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    doc.tag_ner(ner_tagger)
    
    for span in doc.spans:
        span.normalize(morph_vocab)
        # Сопоставляем найденное с оригинальными индексами (упрощенно)
        orig_text = text[span.start:span.stop]
        results.append(Entity(
            text=orig_text, 
            normal=span.normal, 
            start=span.start, 
            end=span.stop, 
            type=span.type
        ))

    # Presidio (Глобальный + РФ паттерны)
    # Расширяем список сущностей (IBAN, IP, CRYPTO, etc.)
    presidio_res = analyzer_en.analyze(
        text=text, 
        language='en', 
        entities=["PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "LOCATION", "IP_ADDRESS", "IBAN_CODE", "RU_INN"],
        score_threshold=0.4
    )
    
    for res in presidio_res:
        # Проверка на пересечение с уже найденными сущностями Natasha
        if not any(r.start <= res.start < r.end for r in results):
            val = text[res.start:res.end]
            results.append(Entity(text=val, normal=val, start=res.start, end=res.end, type=res.entity_type))
            
    return sorted(results, key=lambda x: x.start)
