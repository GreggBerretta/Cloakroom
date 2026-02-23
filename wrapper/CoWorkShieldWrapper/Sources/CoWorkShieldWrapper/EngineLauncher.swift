import Foundation

public enum EngineLauncherError: Error {
    case launchFailed(String)
}

public final class EngineLauncher: @unchecked Sendable {
    private let executableURL: URL
    private let baseArguments: [String]

    public init(
        executableURL: URL = URL(fileURLWithPath: "/usr/bin/env"),
        baseArguments: [String] = ["uv", "run", "cowork-shield"]
    ) {
        self.executableURL = executableURL
        self.baseArguments = baseArguments
    }

    @discardableResult
    public func launchEngine(mode: IPCMode, socketPath: String? = nil) throws -> Process {
        let process = Process()
        process.executableURL = executableURL
        process.arguments = commandArguments(mode: mode, socketPath: socketPath)
        do {
            try process.run()
            return process
        } catch {
            throw EngineLauncherError.launchFailed(error.localizedDescription)
        }
    }

    public func commandArguments(mode: IPCMode, socketPath: String? = nil) -> [String] {
        switch mode {
        case .subprocessStdio:
            return baseArguments + ["ipc-stdio"]
        case .unixDomainSocket:
            if let socketPath, !socketPath.isEmpty {
                return baseArguments + ["ipc-server", "--socket-path", socketPath]
            }
            return baseArguments + ["ipc-server"]
        }
    }
}

