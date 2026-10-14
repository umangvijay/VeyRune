import logging
import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, ConsoleMetricExporter
from typing import Any, Dict

# Set up global OpenTelemetry providers
resource = Resource(attributes={"service.name": "agentic-os"})

# A console exporter is useful while explicitly debugging locally, but it can
# leak prompt/workflow metadata into logs. Production must use a reviewed OTLP
# pipeline; never silently dump spans or metrics to stdout.
_console_export = (
    os.getenv("APP_ENV", "development").lower() != "production"
    and os.getenv("OTEL_CONSOLE_EXPORT", "0").lower() in {"1", "true", "yes"}
)

# Tracing
trace_provider = TracerProvider(resource=resource)
if _console_export:
    trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer("agentic-os.tracer")

# Metrics
metric_readers = (
    [PeriodicExportingMetricReader(ConsoleMetricExporter())] if _console_export else []
)
meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
metrics.set_meter_provider(meter_provider)
meter = metrics.get_meter("agentic-os.meter")

class TelemetrySanitizer:
    """Sanitizes trace attributes to prevent leaking secrets and PII."""
    
    SENSITIVE_KEYS = {
        "api_key", "token", "password", "secret", "authorization",
        "jwt", "credentials", "email", "ssn", "phone", "_approved_request_id"
    }

    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if any(sensitive in k.lower() for sensitive in cls.SENSITIVE_KEYS):
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = cls.sanitize(v)
            return sanitized
        elif isinstance(data, list):
            return [cls.sanitize(item) for item in data]
        # Avoid logging massive strings (e.g. file contents or base64 data)
        elif isinstance(data, str) and len(data) > 2000:
            return data[:1000] + "... [TRUNCATED]"
        return data

def get_tracer():
    return tracer

def get_meter():
    return meter
