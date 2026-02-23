import Foundation

public enum UIBridgeTarget: Sendable {
    case tui
    case gradio
}

public enum UIBridgeLauncherError: Error {
    case launchFailed(String)
}

public final class UIBridgeLauncher: @unchecked Sendable {
    private let executableURL: URL
    private let baseArguments: [String]

    public init(
        executableURL: URL = URL(fileURLWithPath: "/usr/bin/env"),
        baseArguments: [String] = ["uv", "run"]
    ) {
        self.executableURL = executableURL
        self.baseArguments = baseArguments
    }

    @discardableResult
    public func launch(
        target: UIBridgeTarget,
        ipcMode: IPCMode = .default,
        extraEnvironment: [String: String] = [:]
    ) throws -> Process {
        let process = Process()
        process.executableURL = executableURL

        switch target {
        case .tui:
            process.arguments = baseArguments + ["cowork-shield-tui"]
        case .gradio:
            process.arguments = baseArguments + ["cowork-shield-gradio"]
        }

        var env = ProcessInfo.processInfo.environment
        env["CWS_WRAPPER_IPC_MODE"] = ipcMode.rawValue
        for (key, value) in extraEnvironment {
            env[key] = value
        }
        process.environment = env

        do {
            try process.run()
            return process
        } catch {
            throw UIBridgeLauncherError.launchFailed(error.localizedDescription)
        }
    }
}

