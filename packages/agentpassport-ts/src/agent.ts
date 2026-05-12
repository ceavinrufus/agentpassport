// agent.ts
// Agent class with capability registration, trust middleware, and delegation

import { didFromPublicKey, generateKeypair, keypairFromSeed } from "./identity.js";
import { signDelegation } from "./jwt.js";
import { ScopeError, TrustMiddleware } from "./trust.js";
import type { RevocationRegistry } from "./revocation.js";
import type { TaskEnvelope } from "./types.js";

export type CapabilityHandler = (task: TaskEnvelope) => Promise<Record<string, unknown>>;

export interface CapabilityOptions {
  requires?: string[];
}

export interface DelegateOptions {
  targetDid: string;
  scope?: string[];
  ttlSeconds?: number;
}

export class Agent {
  readonly name: string;
  readonly did: string;

  private readonly _privateKey: Uint8Array;
  private readonly _publicKey: Uint8Array;
  private readonly _capabilities = new Map<string, CapabilityHandler>();
  private readonly _capabilityScopes = new Map<string, string[]>();
  private readonly _trustedKeys = new Map<string, Uint8Array>();
  private readonly _trustMiddleware: TrustMiddleware;

  constructor(
    name: string,
    opts: {
      privateKey?: Uint8Array;
      revocationRegistry?: RevocationRegistry;
    } = {}
  ) {
    this.name = name;

    if (opts.privateKey) {
      this._privateKey = opts.privateKey;
      // If 64-byte, last 32 are the public key; if 32-byte seed, derive it
      if (opts.privateKey.length === 64) {
        this._publicKey = opts.privateKey.slice(32);
      } else {
        this._publicKey = keypairFromSeed(opts.privateKey).publicKey;
      }
    } else {
      const kp = generateKeypair();
      this._privateKey = kp.privateKey;
      this._publicKey = kp.publicKey;
    }

    this.did = didFromPublicKey(this._publicKey);

    this._trustMiddleware = new TrustMiddleware(
      this.did,
      this._trustedKeys,
      this._capabilityScopes,
      opts.revocationRegistry
    );
  }

  /**
   * Register a capability handler.
   *
   * @param name     Capability name matched against task.intent.type
   * @param options  Optional { requires: string[] } for scope enforcement
   * @param handler  Async handler function
   */
  capability(
    name: string,
    options: CapabilityOptions,
    handler: CapabilityHandler
  ): this {
    this._capabilities.set(name, handler);
    if (options.requires && options.requires.length > 0) {
      this._capabilityScopes.set(name, options.requires);
    }
    return this;
  }

  /** Register trusted issuer public keys for auth chain verification. */
  trustKeys(keys: Map<string, Uint8Array> | Record<string, Uint8Array>): void {
    const entries =
      keys instanceof Map ? keys.entries() : Object.entries(keys);
    for (const [did, pubKey] of entries) {
      this._trustedKeys.set(did, pubKey);
    }
  }

  /**
   * Handle an incoming task.
   * Runs scope check before dispatching to the capability handler.
   * Throws ScopeError if the auth chain doesn't cover declared scope.
   */
  async handle(task: TaskEnvelope): Promise<Record<string, unknown>> {
    const handler = this._capabilities.get(task.intent.type);
    if (!handler) {
      throw new Error(`No handler for capability: ${task.intent.type}`);
    }

    // Pre-execution scope check — throws ScopeError if violated
    this._trustMiddleware.check(task.auth_chain, task.intent.type);

    return handler(task);
  }

  /**
   * Delegate a task to another agent by signing a new delegation JWT
   * and appending it to the task's auth chain.
   */
  delegate(
    task: TaskEnvelope,
    opts: DelegateOptions
  ): TaskEnvelope {
    const token = signDelegation({
      issuerPrivateKey: this._privateKey,
      issuerDid: this.did,
      subjectDid: opts.targetDid,
      scope: opts.scope ?? ["*"],
      ttlSeconds: opts.ttlSeconds ?? 3600,
    });

    return {
      ...task,
      auth_chain: [...task.auth_chain, token],
      state: "delegated",
    };
  }

  /** Expose this agent's public key (for use by others to trust this agent). */
  get publicKey(): Uint8Array {
    return this._publicKey;
  }
}

export { ScopeError };
