"""Prepare post drafts without HTTP handling or persistence."""

from app.domain.models import Post, User


def prepare_post_draft(*, author: User, content: str) -> Post:
    """Return an unsaved Post with trimmed content for the supplied author.

    Raise ValueError if the author has no positive ID or the content is blank.
    The caller supplies the author; this operation does not look up users.
    """
    if author.id is None or author.id <= 0:
        raise ValueError("Author ID must be a positive integer.")

    trimmed_content = content.strip()
    if not trimmed_content:
        raise ValueError("Content must not be blank.")

    return Post(user_id=author.id, content=trimmed_content)
