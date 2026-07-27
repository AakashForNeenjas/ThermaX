"""Public-safe UI error messages with server-side diagnostic IDs."""

import logging
from uuid import uuid4

logger = logging.getLogger(__name__)


def public_error(context: str, exc: Exception) -> str:
    reference = uuid4().hex[:10]
    logger.exception("%s [reference=%s]", context, reference, exc_info=exc)
    return f"{context}. Reference: {reference}"
