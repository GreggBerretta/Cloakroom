import Foundation
import Darwin

public enum UnixDomainSocketTransportError: Error {
    case socketPathTooLong
    case socketCreateFailed(code: Int32)
    case connectFailed(code: Int32)
    case sendFailed(code: Int32)
    case receiveFailed(code: Int32)
    case partialFrame
    case invalidEnvelope
}

public final class UnixDomainSocketTransport {
    private let socketPath: String
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(socketPath: String) {
        self.socketPath = socketPath
    }

    public func roundTrip(request: IPCEnvelope, timeoutSeconds: Int = 10) throws -> IPCEnvelope {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        if fd < 0 {
            throw UnixDomainSocketTransportError.socketCreateFailed(code: errno)
        }
        defer { close(fd) }

        try setTimeout(fd: fd, seconds: timeoutSeconds)

        var addr = sockaddr_un()
        addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        addr.sun_family = sa_family_t(AF_UNIX)

        let maxPathLength = MemoryLayout.size(ofValue: addr.sun_path)
        if socketPath.utf8.count >= maxPathLength {
            throw UnixDomainSocketTransportError.socketPathTooLong
        }

        withUnsafeMutablePointer(to: &addr.sun_path) { pathPtr in
            pathPtr.withMemoryRebound(to: CChar.self, capacity: maxPathLength) { cPath in
                memset(cPath, 0, maxPathLength)
                _ = socketPath.withCString { src in
                    strncpy(cPath, src, maxPathLength - 1)
                }
            }
        }

        let connectResult = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { saPtr in
                Darwin.connect(fd, saPtr, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        if connectResult != 0 {
            throw UnixDomainSocketTransportError.connectFailed(code: errno)
        }

        let requestBody = try encoder.encode(request)
        let frame = try LengthPrefixedCodec.encode(payload: requestBody)
        try sendAll(fd: fd, data: frame)

        let header = try recvExact(fd: fd, count: LengthPrefixedCodec.headerBytes)
        guard header.count == LengthPrefixedCodec.headerBytes else {
            throw UnixDomainSocketTransportError.partialFrame
        }

        var lengthRaw: UInt64 = 0
        _ = withUnsafeMutableBytes(of: &lengthRaw) { header.copyBytes(to: $0) }
        let bodyLength = Int(UInt64(bigEndian: lengthRaw))

        if bodyLength <= 0 || bodyLength > LengthPrefixedCodec.maxFrameBytes {
            throw UnixDomainSocketTransportError.partialFrame
        }

        let body = try recvExact(fd: fd, count: bodyLength)
        guard body.count == bodyLength else {
            throw UnixDomainSocketTransportError.partialFrame
        }

        do {
            return try decoder.decode(IPCEnvelope.self, from: body)
        } catch {
            throw UnixDomainSocketTransportError.invalidEnvelope
        }
    }

    private func setTimeout(fd: Int32, seconds: Int) throws {
        var timeout = timeval(tv_sec: seconds, tv_usec: 0)
        if setsockopt(
            fd,
            SOL_SOCKET,
            SO_SNDTIMEO,
            &timeout,
            socklen_t(MemoryLayout<timeval>.size)
        ) != 0 {
            throw UnixDomainSocketTransportError.sendFailed(code: errno)
        }
        if setsockopt(
            fd,
            SOL_SOCKET,
            SO_RCVTIMEO,
            &timeout,
            socklen_t(MemoryLayout<timeval>.size)
        ) != 0 {
            throw UnixDomainSocketTransportError.receiveFailed(code: errno)
        }
    }

    private func sendAll(fd: Int32, data: Data) throws {
        var sent = 0
        try data.withUnsafeBytes { rawBuffer in
            guard let base = rawBuffer.baseAddress?.assumingMemoryBound(to: UInt8.self) else {
                return
            }
            while sent < data.count {
                let written = Darwin.send(fd, base.advanced(by: sent), data.count - sent, 0)
                if written <= 0 {
                    throw UnixDomainSocketTransportError.sendFailed(code: errno)
                }
                sent += Int(written)
            }
        }
    }

    private func recvExact(fd: Int32, count: Int) throws -> Data {
        var bytes = [UInt8](repeating: 0, count: count)
        var received = 0

        while received < count {
            let readCount = bytes.withUnsafeMutableBufferPointer { ptr in
                Darwin.recv(fd, ptr.baseAddress!.advanced(by: received), count - received, 0)
            }
            if readCount < 0 {
                throw UnixDomainSocketTransportError.receiveFailed(code: errno)
            }
            if readCount == 0 {
                break
            }
            received += Int(readCount)
        }

        return Data(bytes.prefix(received))
    }
}
