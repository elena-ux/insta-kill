# Week 2 — Preparing a post draft

I added [`prepare_post_draft`](../app/application/post_drafts.py).
The function validates the author ID, trims leading and trailing whitespace,
and rejects blank content. It returns an unsaved `Post`.

The service contains no HTTP or SQLite code and is tested directly as a Python function.

Validation: 8 service tests and one `/health` test.
