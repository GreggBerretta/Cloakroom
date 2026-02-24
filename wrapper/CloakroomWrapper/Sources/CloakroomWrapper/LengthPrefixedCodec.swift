import Foundation

public enum LengthPrefixedCodecError: Error, Equatable {
    case invalidFrameLength(Int)
    case frameTooLarge(Int)
    case partialFrame
}

public enum LengthPrefixedCodec {
    public static let headerBytes = 8
    public static let maxFrameBytes = 16 * 1024 * 1024

    public static func encode(payload: Data) throws -> Data {
        if payload.count <= 0 {
            throw LengthPrefixedCodecError.invalidFrameLength(payload.count)
        }
        if payload.count > maxFrameBytes {
            throw LengthPrefixedCodecError.frameTooLarge(payload.count)
        }

        var length = UInt64(payload.count).bigEndian
        var frame = Data(bytes: &length, count: headerBytes)
        frame.append(payload)
        return frame
    }

    public static func decodeSingle(frame: Data) throws -> Data {
        guard frame.count >= headerBytes else {
            throw LengthPrefixedCodecError.partialFrame
        }

        let declared = Int(frame.prefix(headerBytes).withUnsafeBytes { ptr in
            ptr.load(as: UInt64.self).bigEndian
        })

        if declared <= 0 {
            throw LengthPrefixedCodecError.invalidFrameLength(declared)
        }
        if declared > maxFrameBytes {
            throw LengthPrefixedCodecError.frameTooLarge(declared)
        }

        let body = frame.dropFirst(headerBytes)
        guard body.count == declared else {
            throw LengthPrefixedCodecError.partialFrame
        }

        return Data(body)
    }
}

public final class LengthPrefixedDecoder {
    private var buffer = Data()

    public init() {}

    public func append(_ chunk: Data) throws -> [Data] {
        buffer.append(chunk)
        var decoded: [Data] = []

        while true {
            if buffer.count < LengthPrefixedCodec.headerBytes {
                break
            }

            let length = Int(buffer.prefix(LengthPrefixedCodec.headerBytes).withUnsafeBytes { ptr in
                ptr.load(as: UInt64.self).bigEndian
            })

            if length <= 0 {
                throw LengthPrefixedCodecError.invalidFrameLength(length)
            }
            if length > LengthPrefixedCodec.maxFrameBytes {
                throw LengthPrefixedCodecError.frameTooLarge(length)
            }

            let fullSize = LengthPrefixedCodec.headerBytes + length
            if buffer.count < fullSize {
                break
            }

            let payload = Data(buffer[LengthPrefixedCodec.headerBytes..<fullSize])
            decoded.append(payload)
            buffer.removeFirst(fullSize)
        }

        return decoded
    }

    public func hasPendingBytes() -> Bool {
        !buffer.isEmpty
    }
}
