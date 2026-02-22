import Foundation

public enum WrapperState: String, Sendable {
    case uninitialized = "UNINITIALIZED"
    case engineHandshake = "ENGINE_HANDSHAKE"
    case ready = "READY"
    case busy = "BUSY"
    case hardFail = "HARD_FAIL"
    case shutdown = "SHUTDOWN"
}

public enum WrapperEvent: Sendable {
    case appLaunch
    case handshakeSucceeded
    case handshakeFailed(reason: String)
    case beginOperation(name: String)
    case operationSucceeded
    case operationValidationError(code: String)
    case operationFailed(reason: String)
    case protocolViolation(reason: String)
    case explicitRecovery
    case shutdown
}

public enum WrapperStateMachineError: Error, Equatable {
    case invalidTransition(state: WrapperState, event: String)
}

public final class WrapperStateMachine: @unchecked Sendable {
    private let lock = NSLock()

    public private(set) var state: WrapperState = .uninitialized
    public private(set) var failureReason: String = ""
    public private(set) var inFlightOperation: String = ""

    public init() {}

    @discardableResult
    public func transition(_ event: WrapperEvent) throws -> WrapperState {
        lock.lock()
        defer { lock.unlock() }

        switch (state, event) {
        case (.uninitialized, .appLaunch):
            state = .engineHandshake
            return state

        case (.engineHandshake, .handshakeSucceeded):
            state = .ready
            failureReason = ""
            return state

        case (.engineHandshake, .handshakeFailed(let reason)):
            state = .hardFail
            failureReason = reason
            return state

        case (.ready, .beginOperation(let name)):
            state = .busy
            inFlightOperation = name
            return state

        case (.busy, .operationSucceeded):
            state = .ready
            inFlightOperation = ""
            return state

        case (.busy, .operationValidationError):
            // Expected user-fixable validation boundary.
            state = .ready
            inFlightOperation = ""
            return state

        case (.busy, .operationFailed(let reason)):
            state = .hardFail
            inFlightOperation = ""
            failureReason = reason
            return state

        case (_, .protocolViolation(let reason)):
            state = .hardFail
            inFlightOperation = ""
            failureReason = reason
            return state

        case (.hardFail, .explicitRecovery):
            // Manual recovery path only.
            state = .engineHandshake
            failureReason = ""
            return state

        case (_, .shutdown):
            state = .shutdown
            inFlightOperation = ""
            return state

        default:
            throw WrapperStateMachineError.invalidTransition(
                state: state,
                event: String(describing: event)
            )
        }
    }

    public var canAcceptUserOperations: Bool {
        lock.lock()
        defer { lock.unlock() }
        return state == .ready
    }
}
