import logging

import structlog


def configure_logging(environment: str = "development") -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if environment == "production":
        processors = shared_processors + [structlog.processors.JSONRenderer()]
        log_level = logging.INFO

    else:
        processors = shared_processors + [structlog.dev.ConsoleRenderer(colors=True)]
        log_level = logging.DEBUG

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
