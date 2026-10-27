# API

## Implementate

| Cerere | Răspuns |
| --- | --- |
| `GET /health` | `{"status":"ok"}` |
| `GET /search?q=...&limit=5&mode=semantic` | `{query, mode, results: [{post, score}]}` |

La căutare, `q` este obligatoriu, nu poate fi gol și are cel mult 500 de caractere.
`limit` este între 1 și 50. `mode` este `semantic` sau `keyword`.
Parametrii invalizi primesc `422`; indisponibilitatea modelului primește `503`.

## Planificat: `POST /posts/preview`

Endpointul nu este implementat.

Cerere: `{"author":{"id":7,"username":"elena"},"content":" Hello "}`.

Răspuns așteptat: `{"id":null,"user_id":7,"content":"Hello","created_at":null}`.

Validare: câmpuri obligatorii și tipuri corecte, ID pozitiv, conținut nevid după
eliminarea spațiilor. Erorile de validare vor primi `422`. Postarea nu este salvată.
