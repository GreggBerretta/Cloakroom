# Wrapper Architecture Addendum (Implemented)

Version: 1.1  
Status: Normative (implemented in this repo as protocol + wrapper core)  
Applies To: Phase 2+ macOS Swift Wrapper

## Scope of This Implementation
This repository now includes:
- A strict Python IPC daemon over AF_UNIX with length-prefixed framing.
- A Swift wrapper core package with finite-state-machine controls and anti-false-success gating.
- A runnable Swift invariant harness (`wrapper-invariant-checks`) for release checks.

The full macOS app shell (menu bar UX, hotkeys, full AppKit/SwiftUI orchestration) is still separate from this core.

## Implemented Security/Trust Invariants

### 1) Wrapper-as-Boundary Doctrine
Implemented in wrapper core under:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperStateMachine.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperController.swift`

The wrapper state machine is explicit and disallows undefined transitions.

### 2) Recoverability / Atomicity / Integrity
IPC protocol + daemon enforce:
- strict envelope validation
- strict protocol version match
- length-prefixed framing with partial-frame rejection
- status classification (`SUCCESS`, `VALIDATION_ERROR`, `ERROR`, `HARD_FAIL`)

Implemented in:
- `src/cowork_shield/ipc/protocol.py`
- `src/cowork_shield/ipc/framing.py`
- `src/cowork_shield/ipc/server.py`

### 3) Security Invariant
Clipboard guardrails are implemented in Swift wrapper core:
- clear-before-write placeholder strategy
- changeCount verification
- no automatic plaintext rewrite on failed flow
- launch scrub hook for previous-session signature

Implemented in:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/ClipboardGuard.swift`

### 4) Behavioral Truth / Anti-False-Success
Wrapper success is gated by:
- `status == SUCCESS`
- request ID match
- validated JSON envelope
- workspace identity unchanged
- heartbeat active
- clipboard verification (if applicable)

Implemented in:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/OperationResultGate.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperController.swift`

## State Machine Doctrine (Implemented)
State enum and transitions implemented:
- `UNINITIALIZED`
- `ENGINE_HANDSHAKE`
- `READY`
- `BUSY`
- `HARD_FAIL`
- `SHUTDOWN`

Validation errors transition `BUSY -> READY`; protocol violations and crash-style errors transition to `HARD_FAIL`.

## IPC Architecture (Implemented)
Transport:
- UNIX domain socket (`AF_UNIX`)
- mode `600` on socket path
- framing: `[8-byte big-endian length][JSON payload]`

Envelope requirements enforced:
- `protocol_version`
- `engine_version`
- `request_id`
- `type`
- `workspace_id`
- `workspace_version`
- `payload`

Operations implemented in daemon:
- `HELLO`
- `HEARTBEAT`
- `WORKSPACE_SWITCH`
- `ANONYMIZE_FILE`
- `RESTORE_FILE`
- `CLIPBOARD_ANONYMIZE`
- `CLIPBOARD_RESTORE`
- `VAULT_EXPORT_KEY`
- `VAULT_IMPORT_KEY`
- `STATS_QUERY`
- `INSPECT_COLUMNS`
- `SHUTDOWN`

## Version Negotiation (Implemented)
`HELLO` response includes:
- `protocol_version`
- `engine_version`
- `schema_hash`
- `model_hash`

Schema hash is deterministic and computed from required envelope contract.

## Workspace/Vault Synchronization (Implemented)
Requests require `workspace_id` + `workspace_version`.
- Version mismatch triggers `VALIDATION_ERROR` (`WorkspaceSyncError`).
- Wrapper can treat this as local-state invalidation + re-sync.

Current engine `workspace_version` source: `vault_data.updated_at`.

## Key Management Transport Rule (Implemented)
Wrapper-facing IPC routes exist for:
- `VAULT_EXPORT_KEY`
- `VAULT_IMPORT_KEY`

The wrapper acts as transport only; crypto remains in engine.

## Swift Wrapper Core Package
Path:
- `wrapper/CoWorkShieldWrapper`

Key files:
- `WrapperStateMachine.swift`
- `WrapperController.swift`
- `IPCEnvelope.swift`
- `LengthPrefixedCodec.swift`
- `UnixDomainSocketTransport.swift`
- `ClipboardGuard.swift`

## Testability / Enforcement
Python tests:
- `tests/test_ipc/test_protocol.py`
- `tests/test_ipc/test_framing.py`
- `tests/test_ipc/test_server.py`

Swift invariant harness (toolchain-agnostic, no XCTest dependency):
```bash
cd wrapper/CoWorkShieldWrapper
swift run wrapper-invariant-checks
```

The harness validates:
- state transitions
- framing behavior
- anti-false-success gate
- validation-error return-to-ready path
- clipboard changeCount guard behavior

## Operational Notes
Start IPC daemon from engine:
```bash
uv run cowork-shield ipc-server --socket-path ~/.cowork-shield/ipc/engine.sock
```

The daemon is process-owned by wrapper architecture and intended for wrapper-supervised lifecycle in production.
