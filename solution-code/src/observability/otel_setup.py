"""
TracerProvider + MeterProvider, both exporting to the same OTel Collector.
Every model call and every underwriting session is a span; cost, eval
score, drift score and — new for Module 8 — release variant (stable /
canary / shadow) are all recorded as span attributes and metrics, so a
quality regression introduced by a prompt or model change is visible
through the SAME pipeline as everything else, not a separate system.
"""

import os
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
_resource = Resource.create({"service.name": "sakh-agent"})

_tracer_provider = TracerProvider(resource=_resource)
_tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True)))
trace.set_tracer_provider(_tracer_provider)

_metric_reader = PeriodicExportingMetricReader(
    OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True), export_interval_millis=5000
)
_meter_provider = MeterProvider(resource=_resource, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_meter(name: str):
    return metrics.get_meter(name)
