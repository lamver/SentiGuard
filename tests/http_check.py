"""Проверка живого сервиса по HTTP. python tests/http_check.py http://127.0.0.1:18000"""
import json, sys, time, urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=30) as r:
        return json.loads(r.read())


for _ in range(60):
    try:
        call("/health"); break
    except Exception:
        time.sleep(2)
print("health:", call("/health"))
ents = call("/entities")
print("маркеров:", len(ents))
t = "Отправь документ Ивану Иванову, паспорт 4510 123456, тел. +7 999 123-45-67, ip 95.165.10.22, СНИЛС 112-233-445 95"
t0 = time.time()
for e in call("/analyze", {"text": t}):
    print(f"  {e['type']:14} {e['text']!r} -> {e['normal']!r}")
print(f"время: {int((time.time() - t0) * 1000)} мс")
a = call("/anonymize", {"text": t})
print("маска:", a["text"])
print("назад совпадает:", call("/deanonymize", {"text": a["text"], "items": a["items"]})["text"] == t)
