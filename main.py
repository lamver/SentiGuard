from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import langdetect
from natasha import Segmenter, MorphVocab, NewsEmbedding, NewsMorphGuesser, NewsNamer, Doc
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern

app = FastAPI(title="Sentiguard NLP Engine")

# Инициализация Наташи (RU)
segmenter = Segmenter()
morph_vocab = MorphVocab()
emb = NewsEmbedding()
morph_guesser = NewsMorphGuesser(emb)
namer = NewsNamer(emb)

# Инициализация Presidio (EN + Patterns)
analyzer = AnalyzerEngine(default_score_threshold=0.3)

# Добавляем кастомные паттерны (например, для API-ключей)
api_pattern = Pattern(name="api_key", regex=r"sk-[a-zA-Z0-9]{32,}", score=0.8)
analyzer.registry.add_recognizer(PatternRecognizer(supported_entity="SECRET_KEY", patterns=[api_pattern]))

class Entity(BaseModel):
    text: str
    start: int
    end: int
    type: str
    score: float

class AnalysisRequest(BaseModel):
    text: str

@app.post("/analyze", response_model=List[Entity])
async def analyze_text(request: AnalysisRequest):
    results = []
    text = request.text

    # 1. Детекция русского (Natasha)
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_guesser)
    doc.tag_ner(namer)
    for span in doc.spans:
        results.append(Entity(
            text=span.text, start=span.start, end=span.stop, type=span.type, score=0.95
        ))

    # 2. Детекция международного (Presidio)
    # Ищем: карты, телефоны, email, IP, крипту и т.д.
    presidio_res = analyzer.analyze(
        text=text, 
        language='en', 
        entities=["PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "IP_ADDRESS", "IBAN_CODE", "CRYPTO", "LOCATION", "SECRET_KEY"]
    )
    
    for res in presidio_res:
        # Проверка на перекрытие: если Наташа уже нашла это место, не дублируем
        if not any(r.start <= res.start < r.end for r in results):
            results.append(Entity(
                text=text[res.start:res.end],
                start=res.start,
                end=res.end,
                type=res.entity_type,
                score=res.score
            ))
            
    # Сортируем по позиции в тексте
    return sorted(results, key=lambda x: x.start)

@app.get("/health")
def health():
    return {"status": "ready", "models": ["natasha", "spacy_en", "presidio"]}
