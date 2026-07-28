"""Concurrency helpers shared by graph operations."""

import asyncio


class TaskRegistry:
    """Ensure a named graph node is executed only once per operation."""

    def __init__(self):
        self.tasks = {}
        self.lock = asyncio.Lock()

    async def run_once(self, key, coroutine_factory):
        async with self.lock:
            task = self.tasks.get(key)
            if task is None:
                task = asyncio.ensure_future(coroutine_factory())
                self.tasks[key] = task
        return await task
