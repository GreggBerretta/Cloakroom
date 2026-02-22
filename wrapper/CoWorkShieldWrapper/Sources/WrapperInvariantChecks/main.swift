import Foundation
import CoWorkShieldWrapper

private struct CheckFailure: Error, CustomStringConvertible {
    let description: String
}

private func expect(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    if !condition() {
        throw CheckFailure(description: message)
    }
}

private final class InMemoryClipboardStore: ClipboardStore {
    var changeCount: Int = 0
    var value: String?
    var suppressIncrement = false

    init(_ value: String?) {
        self.value = value
    }

    func readString() -> String? {
        value
    }

    func writeString(_ value: String) throws {
        self.value = value
        if !suppressIncrement {
            changeCount += 1
        }
    }
}

private func checkStateMachine() throws {
    let sm = WrapperStateMachine()
    _ = try sm.transition(.appLaunch)
    _ = try sm.transition(.handshakeSucceeded)
    _ = try sm.transition(.beginOperation(name: "anonymize"))
    _ = try sm.transition(.operationValidationError(code: "ColumnSelectionError"))
    try expect(sm.state == .ready, "State machine failed BUSY -> READY validation transition")

    _ = try sm.transition(.beginOperation(name: "restore"))
    _ = try sm.transition(.operationFailed(reason: "engine crash"))
    try expect(sm.state == .hardFail, "State machine failed BUSY -> HARD_FAIL crash transition")
}

private func checkFraming() throws {
    let payload = Data("hello".utf8)
    let frame = try LengthPrefixedCodec.encode(payload: payload)
    let decoded = try LengthPrefixedCodec.decodeSingle(frame: frame)
    try expect(decoded == payload, "Length-prefixed round-trip mismatch")

    let decoder = LengthPrefixedDecoder()
    let first = frame.prefix(5)
    let second = frame.dropFirst(5)
    let pass1 = try decoder.append(Data(first))
    try expect(pass1.isEmpty, "Incremental decoder parsed a partial frame")
    let pass2 = try decoder.append(Data(second))
    try expect(pass2.count == 1, "Incremental decoder failed to flush full frame")
}

private func checkAntiFalseSuccess() throws {
    let valid = OperationSuccessContext(
        status: "SUCCESS",
        requestIDMatches: true,
        jsonValidated: true,
        workspaceUnchanged: true,
        heartbeatActive: true,
        clipboardVerified: true
    )
    try expect(
        OperationResultGate.canDisplaySuccess(valid),
        "Anti-false-success gate rejected a valid success context"
    )

    let invalid = OperationSuccessContext(
        status: "SUCCESS",
        requestIDMatches: true,
        jsonValidated: true,
        workspaceUnchanged: true,
        heartbeatActive: true,
        clipboardVerified: false
    )
    try expect(
        !OperationResultGate.canDisplaySuccess(invalid),
        "Anti-false-success gate allowed clipboard-unverified success"
    )
}

private func checkControllerValidationPath() throws {
    let stateMachine = WrapperStateMachine()
    _ = try stateMachine.transition(.appLaunch)
    _ = try stateMachine.transition(.handshakeSucceeded)

    let controller = WrapperController(
        stateMachine: stateMachine,
        workspaceID: "default",
        workspaceVersion: "v1"
    )
    try controller.beginOperation(name: "inspect_columns")

    let response = IPCEnvelope(
        protocolVersion: "2.0",
        engineVersion: "0.2.0",
        requestID: "req-1",
        type: "INSPECT_COLUMNS",
        workspaceID: "default",
        workspaceVersion: "v1",
        status: "VALIDATION_ERROR",
        payload: [:],
        errorCode: "ColumnSelectionError",
        errorMessage: "bad column"
    )

    let handled = try controller.handleOperationEnvelope(
        response,
        expectedRequestID: "req-1",
        expectedProtocolVersion: "2.0",
        expectedSchemaHash: "unused",
        clipboardVerified: true
    )
    try expect(!handled, "Controller incorrectly treated VALIDATION_ERROR as success")
    try expect(controller.state == .ready, "Controller failed to return to READY after validation error")
}

private func checkClipboardGuard() throws {
    let store = InMemoryClipboardStore("John Smith")
    let guardrail = ClipboardGuard(store: store, placeholder: "[CLEARED]")
    let tokenized = try guardrail.anonymize { input in
        try expect(input == "John Smith", "Clipboard guard altered plaintext before engine call")
        return "[PERSON_00001]"
    }
    try expect(tokenized == "[PERSON_00001]", "Clipboard anonymize output mismatch")
    try expect(store.changeCount == 2, "Clipboard changeCount validation did not enforce 2 writes")

    let restored = try guardrail.restore { tokenizedInput in
        try expect(tokenizedInput == "[PERSON_00001]", "Clipboard restore input mismatch")
        return "John Smith"
    }
    try expect(restored == "John Smith", "Clipboard restore output mismatch")
}

@main
struct WrapperInvariantChecks {
    static func main() {
        do {
            try checkStateMachine()
            try checkFraming()
            try checkAntiFalseSuccess()
            try checkControllerValidationPath()
            try checkClipboardGuard()
            print("wrapper-invariant-checks: PASS")
        } catch {
            fputs("wrapper-invariant-checks: FAIL - \(error)\n", stderr)
            exit(1)
        }
    }
}
