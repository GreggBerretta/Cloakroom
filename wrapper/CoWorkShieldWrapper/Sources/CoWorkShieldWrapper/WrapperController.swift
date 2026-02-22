import Foundation

public enum WrapperControllerError: Error, Equatable {
    case protocolViolation(String)
    case hardFail(String)
}

public final class WrapperController {
    public static let expectedValidationErrors: Set<String> = [
        "ColumnSelectionError",
        "PdfInputOnlyError",
        "UnsupportedFormatError",
        "WorkspaceSyncError",
        "WorkspaceExpiredError",
        "WorkspaceNotFoundError",
    ]

    private let stateMachine: WrapperStateMachine
    private(set) var workspaceID: String
    private(set) var workspaceVersion: String
    private(set) var heartbeatMisses = 0

    public init(
        stateMachine: WrapperStateMachine = WrapperStateMachine(),
        workspaceID: String,
        workspaceVersion: String
    ) {
        self.stateMachine = stateMachine
        self.workspaceID = workspaceID
        self.workspaceVersion = workspaceVersion
    }

    public var state: WrapperState {
        stateMachine.state
    }

    public func beginOperation(name: String) throws {
        _ = try stateMachine.transition(.beginOperation(name: name))
    }

    @discardableResult
    public func handleOperationEnvelope(
        _ envelope: IPCEnvelope,
        expectedRequestID: String,
        expectedProtocolVersion: String,
        expectedSchemaHash: String,
        clipboardVerified: Bool
    ) throws -> Bool {
        do {
            try envelope.validateResponse(
                expectedRequestID: expectedRequestID,
                expectedProtocolVersion: expectedProtocolVersion,
                expectedSchemaHash: expectedSchemaHash
            )
        } catch {
            _ = try? stateMachine.transition(.protocolViolation(reason: "Envelope validation failed"))
            throw WrapperControllerError.protocolViolation("Envelope validation failed")
        }

        let status = envelope.status ?? ""
        if status == "SUCCESS" {
            let successContext = OperationSuccessContext(
                status: status,
                requestIDMatches: envelope.requestID == expectedRequestID,
                jsonValidated: true,
                workspaceUnchanged: envelope.workspaceID == workspaceID,
                heartbeatActive: heartbeatMisses < 2,
                clipboardVerified: clipboardVerified
            )

            if !OperationResultGate.canDisplaySuccess(successContext) {
                _ = try? stateMachine.transition(.protocolViolation(reason: "anti-false-success"))
                throw WrapperControllerError.protocolViolation(
                    "Anti-false-success gate blocked success state"
                )
            }

            workspaceVersion = envelope.workspaceVersion
            _ = try stateMachine.transition(.operationSucceeded)
            return true
        }

        if status == "VALIDATION_ERROR" {
            let errorCode = envelope.errorCode ?? ""
            if !Self.expectedValidationErrors.contains(errorCode) {
                _ = try? stateMachine.transition(.protocolViolation(reason: "unexpected validation code"))
                throw WrapperControllerError.protocolViolation(
                    "Unexpected validation error code: \(errorCode)"
                )
            }

            _ = try stateMachine.transition(.operationValidationError(code: errorCode))
            return false
        }

        _ = try? stateMachine.transition(.operationFailed(reason: envelope.errorMessage ?? status))
        throw WrapperControllerError.hardFail(envelope.errorMessage ?? "operation failed")
    }

    public func recordHeartbeat(success: Bool) {
        if success {
            heartbeatMisses = 0
            return
        }

        heartbeatMisses += 1
        if heartbeatMisses >= 2 {
            _ = try? stateMachine.transition(
                .operationFailed(reason: "Engine heartbeat lost")
            )
        }
    }

    public func updateWorkspace(id: String, version: String) {
        workspaceID = id
        workspaceVersion = version
    }
}
