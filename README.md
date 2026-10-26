# InstaKill

Programming for AI · Elena Podariu-Ungureanu · 26 octombrie 2026

[Week 2](docs/week02.md): pregătirea unei postări și [contractul API](docs/api-contract.md).
Endpointul de previzualizare rămâne planificat.

## Rulare

Python 3.11+; verificat cu Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

`GET /health` confirmă pornirea aplicației. Teste: `python -m pytest`.
