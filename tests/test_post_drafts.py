import pytest

from app.application.post_drafts import prepare_post_draft
from app.domain.models import Post, User


def test_prepares_unsaved_draft_for_author_without_changing_input():
    author = User(id=7, username="elena")
    original_author = author.model_dump()
    content = " \nSalut, lume!\nÎncă  un rând.\t "

    draft = prepare_post_draft(author=author, content=content)

    assert isinstance(draft, Post)
    assert draft.model_dump() == {
        "id": None,
        "user_id": 7,
        "content": "Salut, lume!\nÎncă  un rând.",
        "created_at": None,
    }
    assert author.model_dump() == original_author


@pytest.mark.parametrize("author_id", [None, 0, -1])
def test_rejects_author_without_positive_id(author_id: int | None):
    author = User(id=author_id, username="elena")

    with pytest.raises(ValueError, match=r"^Author ID must be a positive integer\.$"):
        prepare_post_draft(author=author, content="A draft.")


@pytest.mark.parametrize("content", ["", "   ", "\n\t", "\u2003\u00a0"])
def test_rejects_blank_content(content: str):
    author = User(id=1, username="elena")

    with pytest.raises(ValueError, match=r"^Content must not be blank\.$"):
        prepare_post_draft(author=author, content=content)
