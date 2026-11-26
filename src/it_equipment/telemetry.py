"""OpenTelemetry setup (REQUIREMENTS N4).

The ``mcp`` library already records a span for every MCP request it sends or handles, and
passes the trace context from client to server in each request's ``_meta``. The agent adds
its own spans. All of them are no-ops until a tracer provider is installed; this module
installs one that prints finished spans to the console, but only when ``OTEL_ENABLED`` is
true, so normal output stays readable.

Privacy rule: spans carry only IDs, actions, decisions and codes, never request text,
prompts, model output or secrets.
"""

from __future__ import annotations

from collections.abc import Mapping

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter

from it_equipment.config import otel_enabled


def create_tracer_provider(service_name: str, exporter: SpanExporter) -> TracerProvider:
    """Build a tracer provider that sends each finished span to ``exporter`` right away.

    Args:
        service_name: Names the process in every span, for example ``it-equipment-agent``.
        exporter: Where spans go: the console in normal runs, memory in tests.

    Returns:
        The provider; nothing is installed globally.
    """
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def setup_telemetry(service_name: str, env: Mapping[str, str] | None = None) -> bool:
    """Print this process's spans to the console when ``OTEL_ENABLED`` is true.

    Args:
        service_name: Names the process in every span.
        env: Variables to read. Defaults to the process environment.

    Returns:
        True if telemetry was switched on.
    """
    if not otel_enabled(env):
        return False
    trace.set_tracer_provider(create_tracer_provider(service_name, ConsoleSpanExporter()))
    return True
