import Foundation

public protocol IPCTransport: Sendable {
    func roundTrip(request: IPCEnvelope, timeoutSeconds: Int) throws -> IPCEnvelope
}

