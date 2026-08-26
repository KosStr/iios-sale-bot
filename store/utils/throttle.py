"""Per-user request throttle for callback query handlers.

Prevents duplicate work when a user taps the same button multiple times
before the first response arrives. Each user gets one asyncio.Lock; any
tap that arrives while the lock is held gets an immediate "please wait"
answer and is dropped.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def throttle(func):
    """Drop duplicate callback taps while the handler is still running."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            return await func(update, context)

        lock = _locks[user.id]
        if lock.locked():
            if update.callback_query:
                await update.callback_query.answer("⏳ Зачекайте...")
            return

        async with lock:
            return await func(update, context)

    return wrapper
