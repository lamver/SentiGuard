# 🛡️ SentiGuard NLP Engine

SentiGuard — это высокопроизводительный микросервис для автоматического обнаружения персональных данных (PII) в тексте. Система специально оптимизирована для работы со смешанным русско-английским контентом.

Сервис объединяет возможности библиотеки **Natasha** (для глубокой обработки русского языка с учетом морфологии) и **Microsoft Presidio** (для поиска международных стандартов данных: Email, банковские карты и т.д.).

## Онлайн затестить можно тут 
[https://datahunter.store/tools/text/sensetive/detect](https://datahunter.store/tools/text/sensetive/detect)

## ✨ Основные возможности / Key Features

*   **RU/EN Support:** Одновременная обработка русского и английского языков.
*   **Morphology Awareness:** Определение падежей (Dat, Gen, Loc и др.) и нормализация имен (Ивану -> Иван).
*   **Security First:** Идеально подходит в качестве шлюза перед отправкой данных в LLM (OpenAI, Claude).
*   **Lightweight:** Оптимизирован для работы на CPU, не требует GPU.

---

## 🚀 Быстрый запуск / Quick Start

### Требования / Requirements
*   Docker & Docker Compose

### Запуск / Launch
```bash
docker-compose up --build

🇷🇺 Использование (Russian)
Микросервис предоставляет эндпоинт /analyze, который возвращает координаты сущностей, их тип и грамматические признаки.
Запрос (cURL):

curl -X POST http://localhost:8000/analyze \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Отправь документ для Ивану Иванову из Google в Москве. Почта ivan@google.com"
     }'


     [
  {
    "text": "Ивану Иванову",
    "normal": "Иван Иванов",
    "case": "Dat",
    "start": 21,
    "end": 34,
    "type": "PER"
  },
  {
    "text": "ivan@google.com",
    "normal": "ivan@google.com",
    "case": null,
    "start": 61,
    "end": 76,
    "type": "EMAIL_ADDRESS"
  }
]
