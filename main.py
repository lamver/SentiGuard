from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from natasha import (
    Segmenter, MorphVocab, NewsEmbedding, 
    NewsMorphTagger, NewsSyntaxParser, NewsNERTagger, Doc
)
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider # Добавляем этот импорт

import os

app = FastAPI()

import yaml
with open("languages-config.yml", "r") as f:
    config = yaml.safe_load(f)

# Инициализация Наташи
segmenter = Segmenter()
morph_vocab = MorphVocab()
emb = NewsEmbedding()
morph_tagger = NewsMorphTagger(emb)
ner_tagger = NewsNERTagger(emb)

provider = NlpEngineProvider(nlp_configuration=config)
nlp_engine = provider.create_engine()

# Передаем готовый движок в анализатор
analyzer_en = AnalyzerEngine(nlp_engine=nlp_engine)

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

    # Natasha (Русский)
    doc = Doc(text)
    doc.segment(segmenter)
    doc.tag_morph(morph_tagger)
    doc.tag_ner(ner_tagger)
    for span in doc.spans:
        span.normalize(morph_vocab)
        first_token = next((t for t in doc.tokens if t.start == span.start), None)
        case = first_token.feats.get('Case') if (first_token and hasattr(first_token, 'feats')) else None
        results.append(Entity(text=span.text, normal=span.normal, case=case, start=span.start, end=span.stop, type=span.type))

    # Presidio (Глобальный)
    # Если в Docker переменная задана верно, он НЕ будет ничего качать
    presidio_res = analyzer_en.analyze(text=text, language='en', entities=["PHONE_NUMBER", "CREDIT_CARD", "EMAIL_ADDRESS", "LOCATION"])
    
    for res in presidio_res:
        if not any(r.start <= res.start < r.end for r in results):
            val = text[res.start:res.end]
            results.append(Entity(text=val, normal=val, case=None, start=res.start, end=res.end, type=res.entity_type))
            
    return sorted(results, key=lambda x: x.start)

@app.get("/health")
def health():
    return {"status": "ok"}
