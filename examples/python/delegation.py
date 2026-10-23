"""One signed delegation and a scope check.

The orchestrator grants ``read:records`` to the worker. ``read_record`` runs.
``write_record`` requires ``write:records`` and is rejected before its handler runs.

No network access and no API keys.
"""

from __future__ import annotations

import asyncio

from agentpassport import (
    Agent,
    EventEmitter,
    Intent,
    ScopeError,
    TaskEnvelope,
    generate_keypair,
    sign_delegation,
    verify_auth_chain,
)


async def main() -> None:
    # Agent() logs every task to stdout unless given an emitter.
    quiet = EventEmitter(sinks=[])
    orchestrator_private, _orchestrator_public = generate_keypair()
    orchestrator = Agent(
        "orchestrator",
        private_key=orchestrator_private,
        emitter=quiet,
    )
    worker = Agent("worker", emitter=quiet)
    worker.trust_keys({orchestrator.did: orchestrator.public_key})

    handler_ran: dict[str, bool] = {"write_record": False}

    @worker.capability("read_record", requires=["read:records"])
    async def read_record(task: TaskEnvelope) -> dict[str, str]:
        record_id = str(task.intent.params.get("id", ""))
        return {"record": record_id, "value": "stub"}

    @worker.capability("write_record", requires=["write:records"])
    async def write_record(_task: TaskEnvelope) -> dict[str, bool]:
        handler_ran["write_record"] = True
        return {"written": True}

    token = sign_delegation(
        issuer_private_key=orchestrator_private,
        issuer_did=orchestrator.did,
        subject_did=worker.did,
        scope=["read:records"],
        ttl_seconds=300,
    )
    chain_ok = verify_auth_chain(
        auth_chain=[token],
        expected_subject=worker.did,
        known_public_keys={orchestrator.did: orchestrator.public_key},
    )
    if not chain_ok:
        raise SystemExit("delegation chain did not verify")

    allowed = await worker.handle(
        TaskEnvelope(
            intent=Intent(type="read_record", params={"id": "42"}),
            auth_chain=[token],
        )
    )
    if allowed.get("record") != "42":
        raise SystemExit(f"unexpected read_record result: {allowed}")

    denied: ScopeError | None = None
    try:
        await worker.handle(
            TaskEnvelope(
                intent=Intent(type="write_record", params={"id": "42"}),
                auth_chain=[token],
            )
        )
    except ScopeError as exc:
        denied = exc

    if denied is None:
        raise SystemExit("write_record should have been denied")
    if handler_ran["write_record"]:
        raise SystemExit("write_record handler ran without write:records")
    if "write:records" not in str(denied):
        raise SystemExit(f"scope error did not mention write:records: {denied}")

    print("[orchestrator] signed delegation -> worker | scope: read:records")
    print("chain verified")
    print(f"read_record -> {allowed}")
    print(f"write_record denied: {denied}")
    print("example ok")


if __name__ == "__main__":
    asyncio.run(main())
