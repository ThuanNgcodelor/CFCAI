from apps.tools import reset_conversations as reset_tool


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[str, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query: str, params: tuple[str, ...] | None = None) -> None:
        self.executed.append((" ".join(query.split()), params))


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.autocommit = True

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def _queries(connection: _FakeConnection) -> list[str]:
    return [query for query, _ in connection.cursor_instance.executed]


def test_reset_all_deletes_handoff_tasks_before_conversations(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(reset_tool.psycopg2, "connect", lambda _: connection)

    reset_tool.reset_conversations(reset_all=True)

    queries = _queries(connection)
    assert queries.index("DELETE FROM handoff_tasks;") < queries.index(
        "DELETE FROM conversations;"
    )
    assert "DELETE FROM inbox_events;" in queries
    assert all("ops_audit_log" not in query for query in queries)
    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True


def test_reset_sender_removes_handoff_tasks_by_conversation_scope(monkeypatch) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(reset_tool.psycopg2, "connect", lambda _: connection)

    reset_tool.reset_conversations(sender_id="psid-123")

    executed = connection.cursor_instance.executed
    queries = _queries(connection)
    handoff_index = next(
        index
        for index, query in enumerate(queries)
        if query.startswith("DELETE FROM handoff_tasks")
    )
    conversation_index = queries.index("DELETE FROM conversations WHERE sender_id = %s")
    assert handoff_index < conversation_index
    assert executed[handoff_index][1] == ("psid-123",)
    assert any(
        query.startswith("DELETE FROM outbox_messages WHERE conversation_id IN")
        for query in queries
    )
    assert connection.committed is True
