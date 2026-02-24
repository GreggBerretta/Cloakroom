import Foundation

public struct OperationSuccessContext: Equatable, Sendable {
    public let status: String
    public let requestIDMatches: Bool
    public let jsonValidated: Bool
    public let workspaceUnchanged: Bool
    public let heartbeatActive: Bool
    public let clipboardVerified: Bool

    public init(
        status: String,
        requestIDMatches: Bool,
        jsonValidated: Bool,
        workspaceUnchanged: Bool,
        heartbeatActive: Bool,
        clipboardVerified: Bool
    ) {
        self.status = status
        self.requestIDMatches = requestIDMatches
        self.jsonValidated = jsonValidated
        self.workspaceUnchanged = workspaceUnchanged
        self.heartbeatActive = heartbeatActive
        self.clipboardVerified = clipboardVerified
    }
}

public enum OperationResultGate {
    public static func canDisplaySuccess(_ context: OperationSuccessContext) -> Bool {
        context.status == "SUCCESS"
        && context.requestIDMatches
        && context.jsonValidated
        && context.workspaceUnchanged
        && context.heartbeatActive
        && context.clipboardVerified
    }
}
