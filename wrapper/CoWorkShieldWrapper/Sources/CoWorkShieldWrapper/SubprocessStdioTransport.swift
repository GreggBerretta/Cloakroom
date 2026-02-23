import Foundation

public enum SubprocessStdioTransportError: Error, Equatable {
    case launchFailed(String)
    case timeout
    case missingResponse
    case invalidResponse
    case nonZeroExit(code: Int32, stderr: String)
}

public final class SubprocessStdioTransport: IPCTransport {
    private let executableURL: URL
    private let arguments: [String]
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(
        executableURL: URL = URL(fileURLWithPath: "/usr/bin/env"),
        arguments: [String] = ["uv", "run", "cowork-shield", "ipc-stdio"]
    ) {
        self.executableURL = executableURL
        self.arguments = arguments
    }

    public func roundTrip(request: IPCEnvelope, timeoutSeconds: Int = 10) throws -> IPCEnvelope {
        let process = Process()
        process.executableURL = executableURL
        process.arguments = arguments

        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        do {
            try process.run()
        } catch {
            throw SubprocessStdioTransportError.launchFailed(error.localizedDescription)
        }

        let requestBytes = try encoder.encode(request)
        let frame = try LengthPrefixedCodec.encode(payload: requestBytes)
        stdinPipe.fileHandleForWriting.write(frame)
        try? stdinPipe.fileHandleForWriting.close()

        try waitForExit(process, timeoutSeconds: timeoutSeconds)

        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        let stderrText = String(data: stderrData, encoding: .utf8) ?? ""
        if process.terminationStatus != 0 {
            throw SubprocessStdioTransportError.nonZeroExit(
                code: process.terminationStatus,
                stderr: stderrText
            )
        }

        let stdoutData = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        if stdoutData.isEmpty {
            throw SubprocessStdioTransportError.missingResponse
        }

        do {
            let payloadData = try LengthPrefixedCodec.decodeSingle(frame: stdoutData)
            return try decoder.decode(IPCEnvelope.self, from: payloadData)
        } catch is LengthPrefixedCodecError {
            throw SubprocessStdioTransportError.invalidResponse
        } catch {
            throw SubprocessStdioTransportError.invalidResponse
        }
    }

    private func waitForExit(_ process: Process, timeoutSeconds: Int) throws {
        let group = DispatchGroup()
        group.enter()
        DispatchQueue.global().async {
            process.waitUntilExit()
            group.leave()
        }
        let timedOut = group.wait(timeout: .now() + .seconds(timeoutSeconds)) == .timedOut
        if timedOut {
            process.terminate()
            throw SubprocessStdioTransportError.timeout
        }
    }
}

