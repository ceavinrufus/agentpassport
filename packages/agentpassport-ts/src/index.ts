// index.ts
// Public exports for agentpassport-ts

export {
  // identity
  generateKeypair,
  keypairFromSeed,
  didFromPublicKey,
  parseDid,
  base58btcEncode,
  base58btcDecode,
  type Keypair,
} from "./identity.js";

export {
  // jwt
  signDelegation,
  verifyAuthChain,
  decodeJwtClaims,
  type DelegationClaims,
  type SignDelegationOptions,
  type VerifyAuthChainOptions,
} from "./jwt.js";

export {
  // revocation
  InMemoryRevocationRegistry,
  type RevocationRegistry,
} from "./revocation.js";

export {
  // trust
  TrustMiddleware,
  ScopeError,
} from "./trust.js";

export {
  // agent
  Agent,
  type CapabilityHandler,
  type CapabilityOptions,
  type DelegateOptions,
} from "./agent.js";

export {
  // types
  createTask,
  type TaskEnvelope,
  type TaskState,
  type Intent,
  type Constraints,
} from "./types.js";
