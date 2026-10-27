# Week 3 — Căutare după sens

Am folosit `all-MiniLM-L6-v2` pe CPU pentru a transforma textele în vectori.
Nu am antrenat un model nou.

- [`cosine_similarity`](../app/retrieval.py) compară vectorul întrebării cu vectorii postărilor. Vectorii zero primesc scorul 0.
- [`stable_top_k`](../app/retrieval.py) alege primele rezultate: scor descrescător, apoi ID crescător la egalitate.
- [`SearchService.search`](../app/application/search.py) citește postările, calculează scorurile și construiește răspunsul.

`GET /search?q=inexpensive%20supper&limit=5` caută după sens.
`mode=keyword` compară cuvintele comune.

Encoderul încarcă modelul la prima căutare semantică și îl reutilizează.
Măsurarea timpilor se face separat, în [`evaluate_search.py`](../scripts/evaluate_search.py).
Scriptul măsoară importul, încărcarea modelului și codificarea corpusului înaintea
comparațiilor. Timpii cererilor folosesc modelul deja încărcat și includ recalcularea
vectorilor postărilor.

Pe cele 30 de postări sintetice, căutarea după sens găsește restaurantul
accesibil fără cuvinte comune cu întrebarea. Totuși, pune un restaurant scump
înaintea lui și poate ignora negațiile. Similaritatea nu garantează relevanța.
[Rezultatele măsurate](search-example.json).
