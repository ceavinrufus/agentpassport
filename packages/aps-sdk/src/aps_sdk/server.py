from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from aps_sdk.agent import Agent

from aps_sdk.types.task import TaskEnvelope


def create_agent_app(agent: Agent, verify_auth: bool = False) -> Starlette:
    """Create an ASGI app that dispatches incoming tasks to agent capabilities."""

    async def handle_task(request: Request) -> JSONResponse:
        body = await request.body()
        try:
            task = TaskEnvelope.model_validate_json(body)
        except Exception as e:
            return JSONResponse({"detail": f"Invalid task: {e}"}, status_code=400)

        if verify_auth:
            if not task.auth_chain:
                return JSONResponse({"detail": "Missing auth chain"}, status_code=403)
            from aps_sdk.identity.signing import verify_auth_chain

            valid = verify_auth_chain(
                task.auth_chain,
                expected_subject=agent.did,
                known_public_keys=agent._trusted_keys,
            )
            if not valid:
                return JSONResponse({"detail": "Invalid auth chain"}, status_code=403)

        try:
            result = await agent.handle(task)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse({"detail": f"Handler error: {e}"}, status_code=500)

        return JSONResponse({"task_id": task.id, "state": "completed", "result": result})

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "agent": agent.name, "did": agent.did})

    return Starlette(
        routes=[
            Route("/aps/tasks", handle_task, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
        ]
    )
