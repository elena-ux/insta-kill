# InstaKill

Programming for AI · Elena Podariu-Ungureanu · 26 octombrie 2026

O aplicație socială construită cu FastAPI și SQLite.

- [Week 2](docs/week02.md): pregătirea unei postări.
- [Week 3](docs/week03.md): căutare după sens și după cuvinte.
- [Contract API](docs/api-contract.md): cereri, răspunsuri și erori.

## Rulare

Python 3.11+; verificat cu Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m scripts.seed_db --demo data/demo.db
INSTAKILL_DB_PATH="$PWD/data/demo.db" uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000/docs`. Teste: `python -m pytest`.
Seed-ul creează o bază nouă cu date sintetice și refuză suprascrierea ei.
Prima căutare semantică descarcă modelul pe CPU dacă nu este deja salvat local.
