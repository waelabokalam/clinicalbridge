"""Provider-free tests: orchestration uses stubbed agent responses; retrieval uses fake model/vector adapters."""
import importlib
import sys
from types import ModuleType

import pytest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import StatusCode

from orchestrator.observability import LocalTracing, trace_operation


SECRET = "synthetic-patient@example.invalid symptom-canary credential-canary"


def load_workflow(monkeypatch):
    for name, function in [
        ("triage_agent", "run_triage"), ("ehr_agent", "run_ehr_agent"),
        ("anamnesis_agent", "run_anamnesis_agent"), ("synthesis_agent", "run_synthesis_agent"),
    ]:
        module = ModuleType("agents." + name)
        setattr(module, function, lambda *args, **kwargs: {})
        monkeypatch.setitem(sys.modules, module.__name__, module)
    sys.modules.pop("orchestrator.orchestrator", None)
    workflow = importlib.import_module("orchestrator.orchestrator")
    monkeypatch.setattr(workflow, "INTER_AGENT_DELAY_SECONDS", 0)
    return workflow


def serialized(spans):
    return "\n".join(span.to_json() for span in spans)


def test_disabled_preserves_result_without_exporting():
    telemetry = LocalTracing()
    @trace_operation("orchestrator")
    def run(value):
        return value
    with telemetry.activate():
        assert run(SECRET) == SECRET
    assert telemetry.provider is None and telemetry.exporter is None


def test_real_orchestrator_parentage_redaction_and_no_default_export(monkeypatch):
    workflow = load_workflow(monkeypatch)
    monkeypatch.setattr(workflow, "run_triage", lambda *args: {"urgency": "Routine", "clinical_question": SECRET, "ehr_query": SECRET, "anamnesis_query": SECRET})
    @trace_operation("ehr_retrieval")
    def retrieve(*args):
        return [SECRET]
    monkeypatch.setattr(workflow, "run_ehr_agent", lambda *args: {"documents": retrieve(*args)})
    monkeypatch.setattr(workflow, "run_anamnesis_agent", lambda *args: {"raw_text": SECRET})
    monkeypatch.setattr(workflow, "run_synthesis_agent", lambda *args: {"summary": SECRET})
    telemetry = LocalTracing(enabled=True)
    with telemetry.activate():
        result = workflow.process_alert({"patient_id": SECRET, "alert_id": SECRET})
    assert result["status"] == "completed"
    spans = telemetry.exporter.get_finished_spans()
    root = next(s for s in spans if s.name == "clinicalbridge.orchestrator")
    attempts = [s for s in spans if s.name == "clinicalbridge.agent_attempt"]
    retrieval = next(s for s in spans if s.name == "clinicalbridge.ehr_retrieval")
    assert len(attempts) == 4
    assert all(s.parent.span_id == root.context.span_id for s in attempts)
    assert retrieval.parent.span_id in {s.context.span_id for s in attempts}
    assert retrieval.attributes["clinicalbridge.document_count"] == 1
    assert len({s.context.trace_id for s in spans}) == 1
    assert SECRET not in serialized(spans)
    assert "patient_id" not in serialized(spans)
    assert all(not s.events for s in spans)
    workflow.process_alert({"patient_id": SECRET})
    assert len(telemetry.exporter.get_finished_spans()) == len(spans)
    telemetry.shutdown()


def test_exception_text_and_stack_are_never_exported():
    @trace_operation("ehr_retrieval")
    def fail():
        raise ValueError(SECRET)
    telemetry = LocalTracing(enabled=True)
    with telemetry.activate(), pytest.raises(ValueError, match="symptom-canary"):
        fail()
    span, = telemetry.exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert not span.events and span.status.description is None
    assert SECRET not in serialized([span])
    telemetry.shutdown()


def test_returned_failure_has_error_status():
    @trace_operation("orchestrator")
    def fail():
        return {"status": "failed", "error": SECRET}
    telemetry = LocalTracing(enabled=True)
    with telemetry.activate():
        assert fail()["error"] == SECRET
    span, = telemetry.exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert SECRET not in serialized([span])
    telemetry.shutdown()


def test_offline_export_failure_does_not_break_answers():
    class Offline(SpanExporter):
        def export(self, spans):
            return SpanExportResult.FAILURE
    telemetry = LocalTracing(enabled=True, exporter=Offline())
    @trace_operation("orchestrator")
    def run():
        return {"status": "completed"}
    with telemetry.activate():
        assert run() == {"status": "completed"}
    telemetry.shutdown()


def test_unknown_operation_is_not_accepted_as_a_dynamic_span_name():
    with pytest.raises(ValueError, match="Unregistered"):
        trace_operation(SECRET)


@pytest.mark.parametrize("agent_name", ["ehr_agent", "anamnesis_agent"])
def test_real_retrieval_functions_keep_hard_patient_filter_and_hide_text(monkeypatch, agent_name):
    """Import real retrieval code; fake only external vector/embedding/LLM packages."""
    for package, names in [
        ("langchain_chroma", ["Chroma"]),
        ("langchain_google_genai", ["GoogleGenerativeAIEmbeddings"]),
        ("langchain_core.prompts", ["ChatPromptTemplate"]),
        ("agents.llm_client", ["get_llm"]),
    ]:
        module = ModuleType(package)
        for name in names:
            setattr(module, name, object)
        monkeypatch.setitem(sys.modules, package, module)
    module_name = "agents." + agent_name
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    module = importlib.import_module(module_name)
    calls = []
    class Store:
        def similarity_search(self, query, *, k, filter):
            calls.append((query, k, filter))
            return [type("Document", (), {"page_content": SECRET})()]
    monkeypatch.setattr(module, "get_vectorstore", lambda: Store())
    telemetry = LocalTracing(enabled=True)
    with telemetry.activate():
        assert module.retrieve_chunks("synthetic-patient", SECRET, k=2) == [SECRET]
    assert calls == [(SECRET, 2, {"patient_id": "synthetic-patient"})]
    span, = telemetry.exporter.get_finished_spans()
    assert span.attributes["clinicalbridge.document_count"] == 1
    assert SECRET not in serialized([span]) and "synthetic-patient" not in serialized([span])
    telemetry.shutdown()
