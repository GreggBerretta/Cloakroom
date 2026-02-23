# CoWork Shield Wrapper Architecture (Hybrid IPC, Implemented)

Version: 1.0  
Date: February 2026  
Status: Release-blocking wrapper core implementation landed in this repo  
Applies To: Phase 2.5+ macOS Swift wrapper + current TUI/Gradio compatibility path

## Implemented Against This PRD
This repository now implements a hybrid wrapper protocol surface:

- **Mode A (default):** subprocess + stdin/stdout framed IPC
- **Mode B:** AF_UNIX socket daemon IPC with `600` socket permissions

Core trust invariants remain fail-closed with explicit FSM + anti-false-success gating.

## 1) Hybrid IPC Modes

### Mode A (subprocess stdio)
Implemented in engine:
- `src/cowork_shield/ipc/stdio_server.py`
- CLI command: `cowork-shield ipc-stdio`
- Script entrypoint: `cowork-shield-ipc-stdio`

Implemented in Swift:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/SubprocessStdioTransport.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/HybridIPCClient.swift`
- `IPCMode.default == .subprocessStdio`

### Mode B (AF_UNIX socket)
Implemented in engine:
- `src/cowork_shield/ipc/server.py`
- `src/cowork_shield/ipc/framing.py`
- CLI command: `cowork-shield ipc-server --socket-path ...`

Implemented in Swift:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/UnixDomainSocketTransport.swift`

### Engine launcher mode selection
Implemented in Swift:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/EngineLauncher.swift`

Default launcher command arguments target Mode A (`ipc-stdio`), with Mode B support via `ipc-server`.

## 2) State Machine + Hard-Fail Doctrine
Implemented in:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperStateMachine.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperController.swift`

States:
- `UNINITIALIZED`
- `ENGINE_HANDSHAKE`
- `READY`
- `BUSY`
- `HARD_FAIL`
- `SHUTDOWN`

Validation/business boundary errors return `BUSY -> READY`.  
Protocol/integrity ambiguity transitions to `HARD_FAIL`.

## 3) Payload Parity (Fork Feature Surface)
Protocol/common payload support now validates and accepts:
- `columns`
- `detect_pii`
- `hebrew_backend`
- `pdf_output_format`
- `force_reanonymize`
- `reason`
- `license_key`

Engine protocol schema:
- `src/cowork_shield/ipc/protocol.py`

Swift payload builder:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/OperationPayload.swift`

## 4) License Enforcement Path (Engine-owned)
License is validated by engine on wrapper operations:
- `src/cowork_shield/licensing.py`
- integrated in `src/cowork_shield/ipc/server.py`

Implemented controls:
- free tier restore quota (`5/day`)
- pro-gated features:
  - column-selective anonymization
  - long TTL workspace creation/switch
  - advanced Hebrew backends (`stanza`, `transformers`)
  - audit export operation types

Wrapper receives license metadata in IPC response payload under `payload.license`.

## 5) Handshake Negotiation
`HELLO` payload now returns:
- `protocol_version`
- `engine_version`
- `schema_hash`
- `model_hash`
- `supported_hebrew_backends`
- `supported_pdf_output_formats`
- `supported_ipc_modes`

Engine:
- `src/cowork_shield/ipc/server.py`
- `src/cowork_shield/ipc/protocol.py`

Swift envelope validation checks handshake metadata fields:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/IPCEnvelope.swift`

## 6) Clipboard Security + Anti-False-Success
Implemented in:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/ClipboardGuard.swift`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/OperationResultGate.swift`

Success display remains blocked unless all success predicates are satisfied.

## 7) Sleep/Wake Handling Hook
Wrapper controller now exposes wake-time recovery checks:
- `handleSystemWake(healthCheckPassed:vaultIntegrityPassed:)`
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/WrapperController.swift`

Wake interruption while `BUSY` forces hard-fail to prevent ambiguous completion.

## 8) TUI/Gradio Bridge Launcher
Wrapper-side child-process launcher implemented:
- `wrapper/CoWorkShieldWrapper/Sources/CoWorkShieldWrapper/UIBridgeLauncher.swift`

This provides wrapper-owned process launching for existing Python UIs while preserving engine business-logic ownership.

## 9) Tests and Enforcement
Python:
- `tests/test_ipc/test_protocol.py`
- `tests/test_ipc/test_framing.py`
- `tests/test_ipc/test_server.py`
- `tests/test_ipc/test_stdio_server.py`
- `tests/test_licensing.py`

Swift invariant harness:
```bash
cd wrapper/CoWorkShieldWrapper
swift run wrapper-invariant-checks
```

Harness now validates:
- FSM transitions
- framing integrity
- anti-false-success gate
- Mode A default selection
- payload parity fields
- sleep/wake hard-fail behavior
- launcher mode argument selection

