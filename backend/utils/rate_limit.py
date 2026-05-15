"""Simple in-memory per-user rate limiter."""

import time


RATE_LIMIT = {}
LIMIT = 20  # requests per minute


def check_rate(user):
    """Return False when a user has exceeded LIMIT requests in the last minute."""
    now = time.time()

    if user not in RATE_LIMIT:
        RATE_LIMIT[user] = []

    RATE_LIMIT[user] = [
        t for t in RATE_LIMIT[user]
        # Keep only timestamps inside the rolling 60-second window.
        if now - t < 60
    ]

    if len(RATE_LIMIT[user]) >= LIMIT:
        return False

    RATE_LIMIT[user].append(now)
    return True
