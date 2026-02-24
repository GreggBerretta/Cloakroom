import Foundation

public struct OperationPayload: Sendable, Equatable {
    public var columns: [String]
    public var detectPII: Bool?
    public var detectionMode: String?
    public var hebrewBackend: String?
    public var pdfOutputFormat: String?
    public var forceReanonymize: Bool?
    public var reason: String?
    public var licenseKey: String?

    public init(
        columns: [String] = [],
        detectPII: Bool? = nil,
        detectionMode: String? = nil,
        hebrewBackend: String? = nil,
        pdfOutputFormat: String? = nil,
        forceReanonymize: Bool? = nil,
        reason: String? = nil,
        licenseKey: String? = nil
    ) {
        self.columns = columns
        self.detectPII = detectPII
        self.detectionMode = detectionMode
        self.hebrewBackend = hebrewBackend
        self.pdfOutputFormat = pdfOutputFormat
        self.forceReanonymize = forceReanonymize
        self.reason = reason
        self.licenseKey = licenseKey
    }

    public func toJSONPayload() -> [String: JSONValue] {
        var payload: [String: JSONValue] = [:]
        if !columns.isEmpty {
            payload["columns"] = .array(columns.map { .string($0) })
        }
        if let detectPII {
            payload["detect_pii"] = .bool(detectPII)
        }
        if let detectionMode, !detectionMode.isEmpty {
            payload["detection_mode"] = .string(detectionMode)
        }
        if let hebrewBackend, !hebrewBackend.isEmpty {
            payload["hebrew_backend"] = .string(hebrewBackend)
        }
        if let pdfOutputFormat, !pdfOutputFormat.isEmpty {
            payload["pdf_output_format"] = .string(pdfOutputFormat)
        }
        if let forceReanonymize {
            payload["force_reanonymize"] = .bool(forceReanonymize)
        }
        if let reason, !reason.isEmpty {
            payload["reason"] = .string(reason)
        }
        if let licenseKey {
            payload["license_key"] = .string(licenseKey)
        }
        return payload
    }
}
