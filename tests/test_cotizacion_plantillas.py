import asyncio

from app.modules.cotizacion import router as cotizacion_router


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=()):
        self.sql = " ".join(sql.split())
        self.params = params

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, rows):
        self.fake_cursor = _FakeCursor(rows)
        self.closed = False

    def cursor(self, **_kwargs):
        return self.fake_cursor

    def close(self):
        self.closed = True


def test_get_plantillas_can_include_shared_templates(monkeypatch):
    connection = _FakeConnection([
        {
            "id": "legacy-template",
            "nombre": "Plantilla antigua",
            "vendedor_id": "legacy-owner",
            "es_propia": False,
        }
    ])
    monkeypatch.setattr(cotizacion_router, "_get_connection", lambda: connection)

    result = asyncio.run(
        cotizacion_router.get_plantillas(
            vendedor_id="current-owner",
            incluir_compartidas=True,
        )
    )

    assert result[0]["id"] == "legacy-template"
    assert "WHERE activo = true" in connection.fake_cursor.sql
    assert "AND vendedor_id = %s" not in connection.fake_cursor.sql
    assert connection.fake_cursor.params == ("current-owner",)
    assert connection.closed is True


def test_get_plantillas_keeps_private_filter_by_default(monkeypatch):
    connection = _FakeConnection([])
    monkeypatch.setattr(cotizacion_router, "_get_connection", lambda: connection)

    asyncio.run(cotizacion_router.get_plantillas(vendedor_id="current-owner"))

    assert "AND vendedor_id = %s" in connection.fake_cursor.sql
    assert connection.fake_cursor.params == ("current-owner", "current-owner")

