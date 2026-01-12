import asyncio
from typing import Callable, Any

async def run_in_thread(func: Callable[..., Any], *args, **kwargs) -> Any:
    """Run a blocking function in the default threadpool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
