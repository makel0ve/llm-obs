import pytest
from prometheus_client import REGISTRY, generate_latest

from app.core import metrics  # noqa: F401


@pytest.fixture(autouse=True, scope="session")
def patch_app_engine():
    yield


def test_pipeline_metric_names_are_registered():
    output = generate_latest(REGISTRY).decode()

    assert "llmobs_ingest_batches_accepted_total" in output
    assert "llmobs_ingest_batches_processed_total" in output
    assert "llmobs_ingest_batches_failed_total" in output
    assert "llmobs_ingest_batch_processing_seconds" in output
    assert "llmobs_ingest_spans_dropped_total" in output


def test_worker_modules_share_metric_registry():
    from app.workers import dlq, process_span  # noqa: F401

    output = generate_latest(REGISTRY).decode()

    assert output.count("# HELP llmobs_failed_tasks_total") == 1
