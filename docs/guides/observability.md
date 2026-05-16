# Observability

AgentPassport emits structured events at every significant point in a task's lifecycle. You choose where those events go by registering one or more **sinks** on the agent's `EventEmitter`.

---

## Event model

Every event is an `ObservabilityEvent` with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | `str` | Trace identifier for distributed tracing correlation |
| `task_id` | `str` | Task that produced this event |
| `event` | `str` | Event name (e.g. `task_accepted`, `task_completed`, `state_change`) |
| `from_state` | `str \| None` | Previous state (for `state_change` events) |
| `to_state` | `str \| None` | New state (for `state_change` events) |
| `agent` | `str` | DID of the agent emitting the event |
| `timestamp` | `str` | ISO 8601 UTC timestamp |
| `cost_used` | `float` | Credits spent so far |
| `budget_remaining` | `float` | Credits remaining |
| `metadata` | `dict` | Arbitrary key-value pairs |

Events are emitted automatically by `Agent.handle()`:

| Event name | When |
|-----------|------|
| `task_accepted` | After auth chain verified, before handler called |
| `task_running` | Handler is about to be called |
| `task_completed` | Handler returned successfully |
| `task_failed` | Handler raised an exception |
| `state_change` | Any task lifecycle transition |

---

## Built-in sinks

| Sink | Import | Description |
|------|--------|-------------|
| `StdoutSink` | `agentpassport.observability` | Writes NDJSON to stdout, one event per line |
| `FileSink` | `agentpassport.observability` | Appends NDJSON to a file |
| `MemorySink` | `agentpassport.observability` | Stores events in a list (useful for testing) |
| `OtelSink` | `agentpassport.observability` | Emits OpenTelemetry spans (requires extra install) |

### StdoutSink

```python
from agentpassport.observability import StdoutSink

agent.emitter.add_sink(StdoutSink())
```

Each event is written as a single JSON line to stdout. Useful for local development, or for piping into log aggregators.

### FileSink

```python
from pathlib import Path
from agentpassport.observability import FileSink

agent.emitter.add_sink(FileSink(Path("/var/log/agentpassport/events.ndjson")))
```

The file is opened in append mode on every write. No rotation is built in — use logrotate or a similar tool if needed.

### MemorySink

```python
from agentpassport.observability import MemorySink

sink = MemorySink()
agent.emitter.add_sink(sink)

# After running a task:
for event in sink.events:
    print(event.event, event.task_id)
```

`MemorySink` is primarily designed for testing. All events accumulate in `sink.events` (a plain Python list) for the lifetime of the object.

---

## OtelSink — OpenTelemetry / Datadog integration

`OtelSink` translates each `ObservabilityEvent` into an OpenTelemetry span. You can send these spans to any OTLP-compatible backend: Datadog, Jaeger, Honeycomb, Grafana Tempo, etc.

### Install

```bash
pip install agentpassport[otel]
```

This installs `opentelemetry-api` and `opentelemetry-sdk`. For OTLP export (required for Datadog and most backends) also install the exporter:

```bash
pip install opentelemetry-exporter-otlp-proto-grpc
```

### Configure the OTLP exporter

Set up the OpenTelemetry SDK with an OTLP gRPC exporter before creating your agent. For Datadog, run the Datadog agent with `DD_OTLP_CONFIG_RECEIVER_PROTOCOLS_GRPC_ENDPOINT=0.0.0.0:4317` and point the exporter at `localhost:4317`.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Create a tracer provider with a Datadog-compatible OTLP endpoint
provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
    )
)
trace.set_tracer_provider(provider)
```

### Add OtelSink to an agent

```python
from agentpassport import Agent, generate_keypair, did_from_public_key
from agentpassport.observability import OtelSink

private_key, public_key = generate_keypair()
did = did_from_public_key(public_key)

agent = Agent(name="summariser", did=did, private_key=private_key)

# OtelSink uses the globally configured tracer provider by default
agent.emitter.add_sink(OtelSink())

@agent.capability("summarise", requires=["invoke:llm"])
async def summarise(task):
    # Each call to agent.handle() will emit spans to Datadog
    return {"summary": "..."}
```

If you want to pass a custom tracer instead of using the global one:

```python
from opentelemetry import trace

tracer = trace.get_tracer("my-custom-tracer")
agent.emitter.add_sink(OtelSink(tracer=tracer))
```

### What spans look like

Each `ObservabilityEvent` produces one span named `agentpassport.<event>` (e.g. `agentpassport.task_accepted`). The span carries these attributes:

| Attribute | Value |
|-----------|-------|
| `agentpassport.trace_id` | The task's trace ID |
| `agentpassport.task_id` | The task ID |
| `agentpassport.agent` | The emitting agent's DID |
| `agentpassport.event` | Event name |
| `agentpassport.cost_used` | Credits spent |
| `agentpassport.budget_remaining` | Credits remaining |
| `agentpassport.from_state` | Previous state (state_change events only) |
| `agentpassport.to_state` | New state (state_change events only) |
| `agentpassport.meta.<key>` | Any extra metadata fields |

### Full Datadog example

```python
import asyncio
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from agentpassport import Agent, generate_keypair, did_from_public_key
from agentpassport.observability import OtelSink
from agentpassport.types.task import TaskEnvelope, Intent, Constraints

# 1. Configure OTel to export to the Datadog agent
provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
    )
)
trace.set_tracer_provider(provider)

# 2. Create the agent
priv, pub = generate_keypair()
did = did_from_public_key(pub)
agent = Agent(name="worker", did=did, private_key=priv)
agent.emitter.add_sink(OtelSink())

@agent.capability("echo")
async def echo(task: TaskEnvelope):
    return {"echoed": task.intent.params}

# 3. Handle a task — spans appear in Datadog APM under "agentpassport.*"
async def main():
    task = TaskEnvelope(
        intent=Intent(type="echo", params={"msg": "hello"}),
        constraints=Constraints(),
    )
    result = await agent.handle(task)
    print(result)

asyncio.run(main())
```

---

## Using multiple sinks together

Sinks are additive. Register as many as you need:

```python
from pathlib import Path
from agentpassport.observability import StdoutSink, FileSink, OtelSink

agent.emitter.add_sink(StdoutSink())                               # local dev
agent.emitter.add_sink(FileSink(Path("/tmp/events.ndjson")))       # file backup
agent.emitter.add_sink(OtelSink())                                 # Datadog / Jaeger
```

Sink failures are silently swallowed by `OtelSink` (so observability never crashes your agent). `StdoutSink` and `FileSink` do not catch exceptions — keep that in mind if the target file is on a full disk.

---

## Emitting custom events

Use `agent.emitter.emit()` directly to record application-level events:

```python
agent.emitter.emit(
    trace_id=task.trace_id,
    task_id=task.id,
    event="llm_call",
    agent=agent.did,
    cost_used=0.05,
    budget_remaining=tracker.remaining,
    metadata={"model": "gpt-4o", "tokens": 512},
)
```
