"""HTTP-сервис SentiGuard.

POST /analyze      -> список находок (как раньше: text, normal, case, start, end, type + score, source)
POST /anonymize    -> текст с метками [ФИО_1], [ТЕЛЕФОН_1] и таблица замен
POST /deanonymize  -> вернуть исходные значения по таблице замен
GET  /entities     -> все маркеры, которые реально умеет сервис
GET  /health
"""
import os
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sentiguard.engine import Engine, anonymize, deanonymize

MAX_LEN = int(os.getenv("MAX_TEXT_LEN", "100000"))

app = FastAPI(title="SentiGuard", version="2.0")
engine = Engine()


class Entity(BaseModel):
    text: str
    normal: Optional[str] = None
    case: Optional[str] = None
    start: int
    end: int
    type: str
    score: float
    source: str


class AnalysisRequest(BaseModel):
    text: str
    entities: Optional[List[str]] = None
    score_threshold: float = 0.4


class AnonymizeRequest(AnalysisRequest):
    mode: Literal["tag", "mask", "redact"] = "tag"


class Item(BaseModel):
    placeholder: str
    type: str
    text: str


class AnonymizeResponse(BaseModel):
    text: str
    items: List[Item]
    entities: List[Entity]


class DeanonymizeRequest(BaseModel):
    text: str
    items: List[Item]


def _check(text: str):
    if len(text) > MAX_LEN:
        raise HTTPException(413, f"text longer than {MAX_LEN}")


def _entities(req: AnalysisRequest):
    _check(req.text)
    hits = engine.analyze(req.text, req.entities, req.score_threshold)
    return hits, [Entity(text=req.text[h.start:h.end], normal=h.normal, case=h.case, start=h.start, end=h.end,
                         type=h.type, score=round(h.score, 2), source=h.source) for h in hits]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/entities")
def entities():
    return engine.entity_list()


@app.post("/analyze", response_model=List[Entity])
def analyze(req: AnalysisRequest):
    return _entities(req)[1]


@app.post("/anonymize", response_model=AnonymizeResponse)
def anonymize_ep(req: AnonymizeRequest):
    hits, ents = _entities(req)
    text, items = anonymize(req.text, hits, req.mode)
    return AnonymizeResponse(text=text, items=items, entities=ents)


@app.post("/deanonymize")
def deanonymize_ep(req: DeanonymizeRequest):
    return {"text": deanonymize(req.text, [i.model_dump() for i in req.items])}
