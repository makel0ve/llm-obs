from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator

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
