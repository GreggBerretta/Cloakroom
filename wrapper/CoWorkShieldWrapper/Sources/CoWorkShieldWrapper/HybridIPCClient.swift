import Foundation

public enum IPCMode: String, Sendable {
    case subprocessStdio = "mode_a_stdio"
    case unixDomainSocket = "mode_b_unix_socket"

    public static let `default`: IPCMode = .subprocessStdio
}

public enum HybridIPCClientError: Error {
    case unsupportedMode
}

public final class HybridIPCClient: @unchecked Sendable {
    public let mode: IPCMode
    private let stdioTransport: IPCTransport
    private let socketTransport: IPCTransport

    public init(
        mode: IPCMode = .default,
        stdioTransport: IPCTransport = SubprocessStdioTransport(),
        socketTransport: IPCTransport
    ) {
        self.mode = mode
        self.stdioTransport = stdioTransport
        self.socketTransport = socketTransport
    }

    public func roundTrip(request: IPCEnvelope, timeoutSeconds: Int = 10) throws -> IPCEnvelope {
        switch mode {
        case .subprocessStdio:
            return try stdioTransport.roundTrip(request: request, timeoutSeconds: timeoutSeconds)
        case .unixDomainSocket:
            return try socketTransport.roundTrip(request: request, timeoutSeconds: timeoutSeconds)
        }
    }
}

