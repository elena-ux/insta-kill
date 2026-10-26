# API

`GET /health` returnează `{"status":"ok"}`.

## Planificat: `POST /posts/preview`

Endpointul nu este implementat.

Cerere: `{"author":{"id":7,"username":"elena"},"content":" Hello "}`.

Răspuns așteptat: `{"id":null,"user_id":7,"content":"Hello","created_at":null}`.

Validare: câmpuri obligatorii și tipuri corecte, ID pozitiv, conținut nevid după
eliminarea spațiilor. Erorile de validare vor primi `422`. Postarea nu este salvată.
