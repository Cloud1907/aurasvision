# QA — API Kontrat (Schemathesis) · ofis-qa

> template_version 0.2.0 · AurasVision — Görüntü Analitiği Platformu · Kontrat katmanı (backend_integration'dan ayrı).

OpenAPI şemandan **otomatik yüzlerce sınır/negatif test** üretir; API'yi kırmaya çalışır.
```bash
pip install "schemathesis==4.*"
schemathesis run openapi.json --url http://localhost:5000 --checks all
```
Ön koşul: servisin bir OpenAPI şeması yayması (.NET: Swashbuckle/`swagger.json` · Spring: springdoc). Şema yoksa bu katman çalışmaz.
