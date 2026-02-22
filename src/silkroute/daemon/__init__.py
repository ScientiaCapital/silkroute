"""SilkRoute daemon — persistent service for concurrent agent task execution."""

from silkroute.daemon.queue import TaskQueue, TaskRequest, TaskResult
from silkroute.daemon.redis_pool import close_redis, get_redis
from silkroute.daemon.scheduler import DaemonScheduler

__all__ = [
    "DaemonScheduler",
    "TaskQueue",
    "TaskRequest",
    "TaskResult",
    "close_redis",
    "get_redis",
]
