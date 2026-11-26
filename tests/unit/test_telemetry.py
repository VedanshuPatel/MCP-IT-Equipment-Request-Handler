"""Unit tests for the OpenTelemetry setup (REQUIREMENTS N4).

OpenTelemetry allows one global tracer provider per process, and the test session already
uses it (the ``spans`` fixture), so these tests capture ``set_tracer_provider`` instead of
letting it replace the global one.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from it_equipment.telemetry import create_tracer_provider, setup_telemetry


def test_provider_names_the_service_and_exports_each_finished_span():
    exporter = InMemorySpanExporter()
    provider = create_tracer_provider("it-equipment-test", exporter)

    provider.get_tracer("test").start_span("work").end()

    (span,) = exporter.get_finished_spans()
    assert span.name == "work"
    assert span.resource.attributes["service.name"] == "it-equipment-test"


def test_setup_does_nothing_when_telemetry_is_off(monkeypatch):
    installed = []
    monkeypatch.setattr(trace, "set_tracer_provider", installed.append)

    assert setup_telemetry("it-equipment-agent", env={}) is False
    assert installed == []


def test_setup_installs_a_provider_for_the_service_when_telemetry_is_on(monkeypatch):
    installed = []
    monkeypatch.setattr(trace, "set_tracer_provider", installed.append)

    assert setup_telemetry("it-equipment-agent", env={"OTEL_ENABLED": "true"}) is True
    (provider,) = installed
    assert provider.resource.attributes["service.name"] == "it-equipment-agent"
