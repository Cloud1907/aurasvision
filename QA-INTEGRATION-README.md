# QA — Backend Entegrasyon (Python · testcontainers) · ofis-qa

> template_version 0.2.0 · AurasVision — Görüntü Analitiği Platformu · gerçek PostgreSQL

```bash
pip install pytest "testcontainers[postgres]==4.8.0.*"
pytest test_integration_smoke.py
```
`get_connection_url()` ile uygulamanı gerçek Postgres'e bağla; SQLite/mock ile "entegrasyon" deme. CI'da Docker gerekir.
