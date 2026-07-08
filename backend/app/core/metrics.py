from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

ingest_batches_accepted = Counter(
    "llmobs_ingest_batches_accepted_total",
    "Ingest batches accepted for asynchronous processing",
)
ingest_batches_processed = Counter(
    "llmobs_ingest_batches_processed_total",
    "Ingest batches processed by worker",
    ["status"],
)
ingest_batches_failed = Counter(
    "llmobs_ingest_batches_failed_total",
    "Ingest batches failed before or during worker processing",
    ["stage"],
)
ingest_batch_processing_s = Histogram(
    "llmobs_ingest_batch_processing_seconds",
    "Wall-clock seconds spent processing an ingest batch",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0],
)
ingest_spans_dropped = Counter(
    "llmobs_ingest_spans_dropped_total",
    "Spans dropped during ingest batch processing",
    ["reason"],
)
spans_ingested = Counter(
    "llmobs_spans_ingested_total", "LLM spans ingested", ["provider", "model", "status"]
)
span_processing_s = Histogram(
    "llmobs_span_processing_seconds",
    "Span batch processing time",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)
failed_tasks = Counter(
    "llmobs_failed_tasks_total", "Permanently failed tasks", ["task_name"]
)


def setup_metrics(app):
    Instrumentator().instrument(app).expose(app)
