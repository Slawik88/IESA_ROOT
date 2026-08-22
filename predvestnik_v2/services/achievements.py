"""Read-only compatibility boundary for legacy achievements.

Existing levels and progress remain visible. Runtime events and page views no
longer advance them, grant currencies/items, or feed the old Battle Pass.
"""


async def increment_metric(
    db,
    user_id: int,
    metric_name: str,
    delta: float = 1.0,
    chat_id: int | None = None,
) -> list[dict]:
    """Retired writer boundary; deliberately does not access the database."""
    return []


async def backfill_metric(
    db,
    user_id: int,
    metric_name: str,
    true_value: float,
    chat_id: int | None = None,
) -> list[dict]:
    """Backfill is disabled because a page view must never mint a reward."""
    return []


def format_achievement_notification(grants: list[dict]) -> str:
    """No new grants means there is no runtime notification to render."""
    return ""
