"""JSON serialization for daemon task dataclasses.

Provides round-trip serialize/deserialize for TaskRequest and TaskResult,
using dataclasses.asdict() with a custom encoder for datetime objects.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from silkroute.daemon.queue import TaskRequest, TaskResult


class TaskEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime → ISO 8601 strings."""

    def default(self, o: object) -> object:
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def serialize_request(request: TaskRequest) -> str:
    """Serialize a TaskRequest to a JSON string."""
    return json.dumps(asdict(request), cls=TaskEncoder)


def deserialize_request(data: str) -> TaskRequest:
    """Deserialize a JSON string back to a TaskRequest."""
    d = json.loads(data)
    d["submitted_at"] = datetime.fromisoformat(d["submitted_at"])
    return TaskRequest(**d)


def serialize_result(result: TaskResult) -> str:
    """Serialize a TaskResult to a JSON string."""
    return json.dumps(asdict(result), cls=TaskEncoder)


def deserialize_result(data: str) -> TaskResult:
    """Deserialize a JSON string back to a TaskResult."""
    d = json.loads(data)
    return TaskResult(**d)
