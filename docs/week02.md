# Week 2 — Pregătirea unei postări

Am adăugat [`prepare_post_draft`](../app/application/post_drafts.py).
Funcția verifică ID-ul autorului, elimină spațiile de la capetele textului și
respinge conținutul gol. Returnează un `Post` nesalvat.

Serviciul nu conține HTTP sau SQLite. Endpointul `POST /posts/preview` are
[contractul documentat](api-contract.md), dar nu este implementat.

Verificare: 8 teste pentru serviciu și un test pentru `/health`.
