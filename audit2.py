"""Check if TrustMiddleware._chain_granted_scopes has its own scope escalation gap."""
from agentpassport.agent import Agent
from agentpassport.identity import did_from_public_key, generate_keypair, sign_delegation

def _make_agent():
    priv, pub = generate_keypair()
    did = did_from_public_key(pub)
    return priv, pub, did

# Scenario: orchestrator only gave mid ['read:db']
# mid re-delegates ['read:db', 'admin:*'] to leaf (scope escalation)
# TrustMiddleware on leaf agent should reject this — does it?

orchestrator_priv, orchestrator_pub, orchestrator_did = _make_agent()
mid_priv, mid_pub, mid_did = _make_agent()

leaf_agent = Agent(name="leaf")
leaf_agent.trust_keys({orchestrator_did: orchestrator_pub, mid_did: mid_pub})

from agentpassport.trust import TrustMiddleware, ScopeError
from agentpassport.types.task import Intent, TaskEnvelope
import asyncio

@leaf_agent.capability("sensitive-op", requires=["admin:*"])
async def handle(task):
    return {"ok": True}

# orchestrator grants only ['read:db'] to mid
hop1 = sign_delegation(orchestrator_priv, orchestrator_did, mid_did, ["read:db"])
# mid escalates to ['read:db', 'admin:*'] when delegating to leaf
hop2 = sign_delegation(mid_priv, mid_did, leaf_agent.did, ["read:db", "admin:*"])

task = TaskEnvelope(
    intent=Intent(type="sensitive-op", params={}),
    auth_chain=[hop1, hop2],
)

async def run():
    try:
        result = await leaf_agent.handle(task)
        print(f"BUG — TrustMiddleware accepted escalated scope, handler ran: {result}")
    except ScopeError as e:
        print(f"PASS — ScopeError raised: {e}")

asyncio.run(run())
