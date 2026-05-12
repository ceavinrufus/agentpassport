/**
 * server.ts — agentpassport Demo TypeScript Agent
 *
 * Reads bootstrap.json (written by run_demo.py) to get:
 *   - orchestrator DID + public key (to trust)
 *   - agent private key (own identity)
 *
 * Exposes:
 *   POST /task    — handle a TaskEnvelope
 *   POST /revoke  — register a revoked jti
 *   GET  /health  — liveness check
 */

import http from "http";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

import { Agent, InMemoryRevocationRegistry, ScopeError } from "agentpassport-ts";
import type { TaskEnvelope } from "agentpassport-ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ---------------------------------------------------------------------------
// Bootstrap: read identity config written by run_demo.py
// ---------------------------------------------------------------------------

const bootstrapPath = path.join(__dirname, "..", "bootstrap.json");
const bootstrap = JSON.parse(fs.readFileSync(bootstrapPath, "utf-8")) as {
  orchestrator_did: string;
  orchestrator_public_key_hex: string;
  agent_private_key_hex: string;
};

const agentPrivateKey = Buffer.from(bootstrap.agent_private_key_hex, "hex");
const orchestratorPublicKey = Buffer.from(bootstrap.orchestrator_public_key_hex, "hex");

// ---------------------------------------------------------------------------
// agentpassport Agent setup
// ---------------------------------------------------------------------------

const revocationRegistry = new InMemoryRevocationRegistry();

const agent = new Agent("ts-customer-agent", {
  privateKey: agentPrivateKey,
  revocationRegistry,
});

// Trust the Python orchestrator
agent.trustKeys({ [bootstrap.orchestrator_did]: orchestratorPublicKey });

// Mock DB
const MOCK_CUSTOMERS = [
  { id: 1, name: "Acme Corp", plan: "enterprise" },
  { id: 2, name: "Globex Inc", plan: "starter" },
];

// Capability: read customers — requires read:db:customers scope
agent.capability(
  "queryCustomers",
  { requires: ["read:db:customers"] },
  async (_task) => {
    return { customers: MOCK_CUSTOMERS };
  }
);

// Capability: write customer — requires write:db:customers scope
agent.capability(
  "writeCustomer",
  { requires: ["write:db:customers"] },
  async (task) => {
    return { written: true, record: task.intent.params };
  }
);

// ---------------------------------------------------------------------------
// HTTP server
// ---------------------------------------------------------------------------

const PORT = parseInt(process.env.AGENTPASSPORT_AGENT_PORT ?? "7700", 10);

function readBody(req: http.IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

function send(
  res: http.ServerResponse,
  status: number,
  body: unknown
): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

const server = http.createServer(async (req, res) => {
  const url = req.url ?? "/";
  const method = req.method ?? "GET";

  try {
    if (method === "GET" && url === "/health") {
      send(res, 200, { ok: true, did: agent.did });
      return;
    }

    if (method === "POST" && url === "/revoke") {
      const body = (await readBody(req)) as { jti: string };
      revocationRegistry.revoke(body.jti);
      send(res, 200, { ok: true });
      return;
    }

    if (method === "POST" && url === "/task") {
      const task = (await readBody(req)) as TaskEnvelope;
      try {
        const result = await agent.handle(task);
        send(res, 200, { result });
      } catch (e) {
        if (e instanceof ScopeError) {
          send(res, 403, {
            error: "scope_denied",
            message: (e as Error).message,
            capability: e.capability,
            required: e.required,
            granted: e.granted,
          });
        } else {
          send(res, 403, {
            error: "auth_chain_invalid",
            message: (e as Error).message,
          });
        }
      }
      return;
    }

    send(res, 404, { error: "not_found" });
  } catch (e) {
    send(res, 500, { error: "internal", message: (e as Error).message });
  }
});

server.listen(PORT, "127.0.0.1", () => {
  process.stdout.write(`AGENTPASSPORT_AGENT_READY port=${PORT} did=${agent.did}\n`);
});
