import base64
from datetime import UTC, datetime

import pytest

from app.services.trace_service import decode_trace_cursor, encode_trace_cursor


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine() -> None:
    return None


def test_trace_cursor_round_trips_timestamp_with_delimiters() -> None:
    started_at = datetime(2026, 7, 16, 12, 34, 56, 789000, tzinfo=UTC)
    trace_id = "0af76519-16cd-43dd-8448-eb211c80319c"

    cursor = encode_trace_cursor(started_at, trace_id)
    decoded_started_at, decoded_trace_id = decode_trace_cursor(cursor)

    assert decoded_started_at == started_at
    assert decoded_trace_id == trace_id


def test_trace_cursor_decodes_legacy_cursor_with_timestamp_delimiters() -> None:
    started_at = datetime(2026, 7, 16, 12, 34, 56, 789000, tzinfo=UTC)
    trace_id = "0af76519-16cd-43dd-8448-eb211c80319c"
    raw = f"{started_at.isoformat()}:{trace_id}"
    legacy_cursor = base64.b64encode(raw.encode()).decode()

    decoded_started_at, decoded_trace_id = decode_trace_cursor(legacy_cursor)

    assert decoded_started_at == started_at
    assert decoded_trace_id == trace_id


def test_trace_cursor_rejects_invalid_cursor() -> None:
    with pytest.raises(ValueError, match="Invalid pagination cursor"):
        decode_trace_cursor("not-a-valid-cursor")
