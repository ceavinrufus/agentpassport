// types.ts
// Core APS types — wire-compatible with Python SDK

export type TaskState =
  | "created"
  | "delegated"
  | "accepted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface Intent {
  type: string;
  params: Record<string, unknown>;
}

export interface Constraints {
  budget_credits: number;
  deadline_ms?: number;
  max_delegations: number;
  allowed_capabilities: string[];
  denied_capabilities: string[];
}

export interface TaskEnvelope {
  aps_version: "1.0";
  id: string;
  parent_id?: string;
  intent: Intent;
  constraints: Constraints;
  /** List of EdDSA JWT strings forming the delegation chain */
  auth_chain: string[];
  trace_id: string;
  state: TaskState;
}

/** Convenience factory for creating a new TaskEnvelope. */
export function createTask(
  intent: Intent,
  overrides: Partial<Omit<TaskEnvelope, "aps_version" | "intent">> = {}
): TaskEnvelope {
  return {
    aps_version: "1.0",
    id: crypto.randomUUID(),
    intent,
    constraints: {
      budget_credits: 100,
      max_delegations: 5,
      allowed_capabilities: [],
      denied_capabilities: [],
      ...overrides.constraints,
    },
    auth_chain: [],
    trace_id: crypto.randomUUID(),
    state: "created",
    ...overrides,
  };
}
