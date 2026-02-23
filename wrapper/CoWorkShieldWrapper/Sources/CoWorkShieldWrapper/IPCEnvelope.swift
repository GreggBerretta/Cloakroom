import Foundation

public enum JSONValue: Codable, Equatable, Sendable {
    case object([String: JSONValue])
    case array([JSONValue])
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
            return
        }
        if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
            return
        }
        if let value = try? container.decode(String.self) {
            self = .string(value)
            return
        }
        if let value = try? container.decode(Double.self) {
            self = .number(value)
            return
        }
        if let value = try? container.decode(Bool.self) {
            self = .bool(value)
            return
        }
        if container.decodeNil() {
            self = .null
            return
        }
        throw IPCEnvelopeValidationError.invalidJSONValue
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    public var stringValue: String? {
        if case let .string(value) = self {
            return value
        }
        return nil
    }

    public var arrayValue: [JSONValue]? {
        if case let .array(value) = self {
            return value
        }
        return nil
    }
}

public struct IPCEnvelope: Codable, Equatable, Sendable {
    public let protocolVersion: String
    public let engineVersion: String
    public let requestID: String
    public let type: String
    public let workspaceID: String
    public let workspaceVersion: String
    public let status: String?
    public let payload: [String: JSONValue]
    public let errorCode: String?
    public let errorMessage: String?

    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol_version"
        case engineVersion = "engine_version"
        case requestID = "request_id"
        case type
        case workspaceID = "workspace_id"
        case workspaceVersion = "workspace_version"
        case status
        case payload
        case errorCode = "error_code"
        case errorMessage = "error_message"
    }

    public init(
        protocolVersion: String,
        engineVersion: String,
        requestID: String,
        type: String,
        workspaceID: String,
        workspaceVersion: String,
        status: String? = nil,
        payload: [String: JSONValue],
        errorCode: String? = nil,
        errorMessage: String? = nil
    ) {
        self.protocolVersion = protocolVersion
        self.engineVersion = engineVersion
        self.requestID = requestID
        self.type = type
        self.workspaceID = workspaceID
        self.workspaceVersion = workspaceVersion
        self.status = status
        self.payload = payload
        self.errorCode = errorCode
        self.errorMessage = errorMessage
    }

    public func validateResponse(
        expectedRequestID: String,
        expectedProtocolVersion: String,
        expectedSchemaHash: String
    ) throws {
        if protocolVersion != expectedProtocolVersion {
            throw IPCEnvelopeValidationError.protocolMismatch(
                expected: expectedProtocolVersion,
                actual: protocolVersion
            )
        }
        if requestID != expectedRequestID {
            throw IPCEnvelopeValidationError.requestIDMismatch(
                expected: expectedRequestID,
                actual: requestID
            )
        }
        guard let status, !status.isEmpty else {
            throw IPCEnvelopeValidationError.missingField("status")
        }
        guard !workspaceID.isEmpty else {
            throw IPCEnvelopeValidationError.missingField("workspace_id")
        }

        if type.uppercased() == "HELLO" {
            guard let schemaHash = payload["schema_hash"]?.stringValue, !schemaHash.isEmpty else {
                throw IPCEnvelopeValidationError.missingField("payload.schema_hash")
            }
            if schemaHash != expectedSchemaHash {
                throw IPCEnvelopeValidationError.schemaHashMismatch(
                    expected: expectedSchemaHash,
                    actual: schemaHash
                )
            }
            guard let hebrewBackends = payload["supported_hebrew_backends"]?.arrayValue,
                !hebrewBackends.isEmpty
            else {
                throw IPCEnvelopeValidationError.missingField("payload.supported_hebrew_backends")
            }
            guard let ipcModes = payload["supported_ipc_modes"]?.arrayValue, !ipcModes.isEmpty else {
                throw IPCEnvelopeValidationError.missingField("payload.supported_ipc_modes")
            }
        }
    }
}

public enum IPCEnvelopeValidationError: Error, Equatable {
    case missingField(String)
    case protocolMismatch(expected: String, actual: String)
    case requestIDMismatch(expected: String, actual: String)
    case schemaHashMismatch(expected: String, actual: String)
    case invalidJSONValue
}
