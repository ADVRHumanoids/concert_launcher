"""Deduplicate concurrent work while traversing dependency graphs."""

import asyncio


class TaskRegistry:
    """Ensure a named graph node is executed only once per operation."""

    def __init__(self):
        self.tasks = {}
        self.lock = asyncio.Lock()

    async def run_once(self, key, coroutine_factory):
        """Create one task per key and let every caller await that task."""
        # Dependency graphs can converge on the same node. Register the task
        # under a lock so concurrent parents share one execution rather than
        # starting duplicate processes or stop operations.
        async with self.lock:
            task = self.tasks.get(key)
            if task is None:
                task = asyncio.ensure_future(coroutine_factory())
                self.tasks[key] = task
        return await task
