import AppKit
import Carbon.HIToolbox
import CloakroomWrapper
import Foundation
import ServiceManagement

private enum MenuConstants {
    static let protocolVersion = "2.0"
    static let engineVersion = "0.2.0"
    static let defaultWorkspace = "default"
    static let pricingURL = "https://cloakroom.ai/pricing"
    static let launchAtLoginKey = "cloakroom_launch_at_login"
    static let crashReportingKey = "cloakroom_crash_reporting_opt_in"
    static let licenseKeyStorageKey = "cloakroom_license_key"
    static let clipboardShieldKeyCode: UInt16 = 1   // S
    static let clipboardRestoreKeyCode: UInt16 = 15 // R
}

private enum PasteboardClipboardStoreError: Error {
    case writeFailed
}

private final class PasteboardClipboardStore: ClipboardStore {
    private let pasteboard: NSPasteboard

    init(pasteboard: NSPasteboard = .general) {
        self.pasteboard = pasteboard
    }

    var changeCount: Int {
        pasteboard.changeCount
    }

    func readString() -> String? {
        pasteboard.string(forType: .string)
    }

    func writeString(_ value: String) throws {
        pasteboard.clearContents()
        guard pasteboard.setString(value, forType: .string) else {
            throw PasteboardClipboardStoreError.writeFailed
        }
    }
}

private enum MenuBarOperationError: Error {
    case validationHandled(String)
    case missingPayload(String)
    case invalidHeartbeat
}

@main
struct CloakroomMenuBarMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = CloakroomMenuBarDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}

@MainActor
final class CloakroomMenuBarDelegate: NSObject, NSApplicationDelegate {
    private let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let menu = NSMenu()
    private let uiLauncher = UIBridgeLauncher()
    private let updateManager = UpdateManager()
    private let crashReporter = LocalCrashReporter()
    private let defaults = UserDefaults.standard
    private lazy var clipboardGuard = ClipboardGuard(store: PasteboardClipboardStore())

    private lazy var ipcClient: HybridIPCClient = {
        let socketPath = "\(NSHomeDirectory())/.cloakroom/ipc/engine.sock"
        return HybridIPCClient(
            mode: .default,
            stdioTransport: SubprocessStdioTransport(),
            socketTransport: UnixDomainSocketTransport(socketPath: socketPath)
        )
    }()

    private let stateMachine = WrapperStateMachine()
    private lazy var controller: WrapperController = {
        WrapperController(
            stateMachine: stateMachine,
            workspaceID: MenuConstants.defaultWorkspace,
            workspaceVersion: ""
        )
    }()

    private var workspaceName: String = MenuConstants.defaultWorkspace
    private var licenseKey: String = ""
    private var globalMonitor: Any?
    private var localMonitor: Any?

    private var launchAtLoginEnabled: Bool {
        get { defaults.bool(forKey: MenuConstants.launchAtLoginKey) }
        set { defaults.set(newValue, forKey: MenuConstants.launchAtLoginKey) }
    }

    private var crashReportingEnabled: Bool {
        get { defaults.bool(forKey: MenuConstants.crashReportingKey) }
        set { defaults.set(newValue, forKey: MenuConstants.crashReportingKey) }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        _ = notification
        licenseKey = defaults.string(forKey: MenuConstants.licenseKeyStorageKey) ?? ""
        setupMenu()
        installLifecycleObservers()
        installHotkeyMonitors()
        configureLaunchAtLoginIfNeeded()
        crashReporter.install(optedIn: crashReportingEnabled)
        performStartupHandshake()
        switchWorkspace(to: workspaceName)
    }

    func applicationWillTerminate(_ notification: Notification) {
        _ = notification
        if let globalMonitor {
            NSEvent.removeMonitor(globalMonitor)
        }
        if let localMonitor {
            NSEvent.removeMonitor(localMonitor)
        }
    }

    private func setupMenu() {
        if let button = statusItem.button {
            button.title = "Shield: \(workspaceName)"
        }

        menu.removeAllItems()
        menu.addItem(withTitle: "Shield Clipboard    ⌘⇧S", action: #selector(shieldClipboard), keyEquivalent: "")
        menu.addItem(withTitle: "Restore Clipboard   ⌘⇧R", action: #selector(restoreClipboard), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Switch Workspace…", action: #selector(promptWorkspace), keyEquivalent: "")
        menu.addItem(withTitle: "Set License Key…", action: #selector(promptLicenseKey), keyEquivalent: "")

        let launchItem = NSMenuItem(
            title: "Launch at Login",
            action: #selector(toggleLaunchAtLogin),
            keyEquivalent: ""
        )
        launchItem.state = launchAtLoginEnabled ? .on : .off
        menu.addItem(launchItem)

        let crashItem = NSMenuItem(
            title: "Crash Reporting (Opt-In)",
            action: #selector(toggleCrashReporting),
            keyEquivalent: ""
        )
        crashItem.state = crashReportingEnabled ? .on : .off
        menu.addItem(crashItem)

        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Open TUI", action: #selector(openTUI), keyEquivalent: "")
        menu.addItem(withTitle: "Open Gradio", action: #selector(openGradio), keyEquivalent: "")
        menu.addItem(withTitle: "Check for Updates…", action: #selector(checkForUpdates), keyEquivalent: "")
        menu.addItem(NSMenuItem.separator())
        menu.addItem(withTitle: "Quit", action: #selector(quitApp), keyEquivalent: "q")

        statusItem.menu = menu
    }

    private func installLifecycleObservers() {
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(handleWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
    }

    private func installHotkeyMonitors() {
        let handler: (NSEvent) -> Void = { [weak self] event in
            guard let self else { return }
            let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
            let expectsFlags: NSEvent.ModifierFlags = [.command, .shift]
            guard flags.contains(expectsFlags) else { return }

            if event.keyCode == MenuConstants.clipboardShieldKeyCode {
                self.shieldClipboard()
            } else if event.keyCode == MenuConstants.clipboardRestoreKeyCode {
                self.restoreClipboard()
            }
        }
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown, handler: handler)
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            handler(event)
            return event
        }
    }

    private func configureLaunchAtLoginIfNeeded() {
        guard #available(macOS 13.0, *) else {
            return
        }
        do {
            if launchAtLoginEnabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            crashReporter.record(
                error: error,
                context: ["component": "launch_at_login"]
            )
        }
    }

    private func performStartupHandshake() {
        do {
            _ = try stateMachine.transition(.appLaunch)
            let requestID = UUID().uuidString
            let request = IPCEnvelope(
                protocolVersion: MenuConstants.protocolVersion,
                engineVersion: MenuConstants.engineVersion,
                requestID: requestID,
                type: "HELLO",
                workspaceID: workspaceName,
                workspaceVersion: controller.currentWorkspaceVersion,
                payload: [:]
            )
            let response = try ipcClient.roundTrip(request: request, timeoutSeconds: 15)
            let schemaHash = response.payload["schema_hash"]?.stringValue ?? ""
            _ = try controller.handleOperationEnvelope(
                response,
                expectedRequestID: requestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: schemaHash,
                clipboardVerified: true
            )
            setStatusSubtitle("READY")
        } catch {
            setStatusSubtitle("HARD_FAIL")
            crashReporter.record(error: error, context: ["stage": "handshake"])
        }
    }

    private func switchWorkspace(to name: String) {
        do {
            try controller.beginOperation(name: "workspace_switch")
            let requestID = UUID().uuidString
            let payload: [String: JSONValue] = [
                "create_if_missing": .bool(true),
                "ttl_hours": .number(24),
            ]
            let request = IPCEnvelope(
                protocolVersion: MenuConstants.protocolVersion,
                engineVersion: MenuConstants.engineVersion,
                requestID: requestID,
                type: "WORKSPACE_SWITCH",
                workspaceID: name,
                workspaceVersion: controller.currentWorkspaceVersion,
                payload: payloadWithLicense(payload)
            )
            let response = try ipcClient.roundTrip(request: request, timeoutSeconds: 15)
            _ = try controller.handleOperationEnvelope(
                response,
                expectedRequestID: requestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: "unused",
                clipboardVerified: true
            )
            if let workspaceID = response.payload["workspace_id"]?.stringValue {
                controller.updateWorkspace(id: workspaceID, version: response.workspaceVersion)
            } else {
                controller.updateWorkspace(id: name, version: response.workspaceVersion)
            }
            workspaceName = response.payload["workspace_name"]?.stringValue ?? name
            if let button = statusItem.button {
                button.title = "Shield: \(workspaceName)"
            }
            setStatusSubtitle("READY")
        } catch {
            setStatusSubtitle("HARD_FAIL")
            crashReporter.record(error: error, context: ["stage": "workspace_switch"])
        }
    }

    @objc private func handleWake() {
        do {
            let engineHealthy = runHeartbeatProbe(recordResult: false)
            let vaultHealthy = runVaultIntegrityProbe()
            try controller.handleSystemWake(
                healthCheckPassed: engineHealthy,
                vaultIntegrityPassed: vaultHealthy
            )
            setStatusSubtitle("READY")
        } catch {
            setStatusSubtitle("HARD_FAIL")
            crashReporter.record(error: error, context: ["stage": "wake_check"])
        }
    }

    @objc private func shieldClipboard() {
        runGuardedClipboardOperation(requestType: "TEXT_ANONYMIZE", restore: false)
    }

    @objc private func restoreClipboard() {
        runGuardedClipboardOperation(requestType: "TEXT_RESTORE", restore: true)
    }

    private func runGuardedClipboardOperation(requestType: String, restore: Bool) {
        do {
            try controller.beginOperation(name: requestType.lowercased())

            var successRequestID = ""
            var successResponse: IPCEnvelope?
            let transform: (String) throws -> String = { [weak self] input in
                guard let self else { throw MenuBarOperationError.missingPayload("delegate") }
                let result = try self.requestTextTransform(requestType: requestType, text: input)
                successRequestID = result.requestID
                successResponse = result.response
                return result.text
            }

            if restore {
                _ = try clipboardGuard.restore(engineTransform: transform)
            } else {
                _ = try clipboardGuard.anonymize(engineTransform: transform)
            }

            guard let response = successResponse else {
                throw MenuBarOperationError.missingPayload("response")
            }
            guard runHeartbeatProbe(recordResult: true) else {
                throw MenuBarOperationError.invalidHeartbeat
            }
            _ = try controller.handleOperationEnvelope(
                response,
                expectedRequestID: successRequestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: "unused",
                clipboardVerified: true
            )
            controller.updateWorkspace(
                id: controller.currentWorkspaceID,
                version: response.workspaceVersion
            )
            setStatusSubtitle("READY")
        } catch MenuBarOperationError.validationHandled {
            setStatusSubtitle("READY")
        } catch {
            setStatusSubtitle("HARD_FAIL")
            crashReporter.record(error: error, context: ["stage": requestType.lowercased()])
        }
    }

    private func requestTextTransform(
        requestType: String,
        text: String
    ) throws -> (requestID: String, response: IPCEnvelope, text: String) {
        let requestID = UUID().uuidString
        let request = IPCEnvelope(
            protocolVersion: MenuConstants.protocolVersion,
            engineVersion: MenuConstants.engineVersion,
            requestID: requestID,
            type: requestType,
            workspaceID: controller.currentWorkspaceID,
            workspaceVersion: controller.currentWorkspaceVersion,
            payload: payloadWithLicense(["text": .string(text)])
        )
        let response = try ipcClient.roundTrip(request: request, timeoutSeconds: 20)
        try response.validateResponse(
            expectedRequestID: requestID,
            expectedProtocolVersion: MenuConstants.protocolVersion,
            expectedSchemaHash: "unused"
        )

        if response.status != "SUCCESS" {
            _ = try controller.handleOperationEnvelope(
                response,
                expectedRequestID: requestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: "unused",
                clipboardVerified: false
            )
            throw MenuBarOperationError.validationHandled(response.errorMessage ?? requestType)
        }

        guard let transformedText = response.payload["text"]?.stringValue else {
            throw MenuBarOperationError.missingPayload("payload.text")
        }
        return (requestID, response, transformedText)
    }

    private func runHeartbeatProbe(recordResult: Bool = true) -> Bool {
        let requestID = UUID().uuidString
        let request = IPCEnvelope(
            protocolVersion: MenuConstants.protocolVersion,
            engineVersion: MenuConstants.engineVersion,
            requestID: requestID,
            type: "HEARTBEAT",
            workspaceID: controller.currentWorkspaceID,
            workspaceVersion: controller.currentWorkspaceVersion,
            payload: payloadWithLicense([:])
        )

        do {
            let response = try ipcClient.roundTrip(request: request, timeoutSeconds: 10)
            try response.validateResponse(
                expectedRequestID: requestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: "unused"
            )
            let healthy = response.status == "SUCCESS"
                && response.payload["alive"]?.boolValue == true
                && response.payload["protocol_version"]?.stringValue == MenuConstants.protocolVersion
            if recordResult {
                controller.recordHeartbeat(success: healthy)
            }
            return healthy
        } catch {
            if recordResult {
                controller.recordHeartbeat(success: false)
            }
            crashReporter.record(error: error, context: ["stage": "heartbeat"])
            return false
        }
    }

    private func runVaultIntegrityProbe() -> Bool {
        let requestID = UUID().uuidString
        let request = IPCEnvelope(
            protocolVersion: MenuConstants.protocolVersion,
            engineVersion: MenuConstants.engineVersion,
            requestID: requestID,
            type: "STATS_QUERY",
            workspaceID: controller.currentWorkspaceID,
            workspaceVersion: controller.currentWorkspaceVersion,
            payload: payloadWithLicense([:])
        )

        do {
            let response = try ipcClient.roundTrip(request: request, timeoutSeconds: 10)
            try response.validateResponse(
                expectedRequestID: requestID,
                expectedProtocolVersion: MenuConstants.protocolVersion,
                expectedSchemaHash: "unused"
            )
            return response.status == "SUCCESS"
        } catch {
            crashReporter.record(error: error, context: ["stage": "vault_integrity_probe"])
            return false
        }
    }

    @objc private func promptWorkspace() {
        let alert = NSAlert()
        alert.messageText = "Switch Workspace"
        alert.informativeText = "Enter workspace name."
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
        input.stringValue = workspaceName
        alert.accessoryView = input
        alert.addButton(withTitle: "Switch")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            let value = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            if !value.isEmpty {
                switchWorkspace(to: value)
            }
        }
    }

    @objc private func promptLicenseKey() {
        let alert = NSAlert()
        alert.messageText = "License Key"
        alert.informativeText = "Optional Pro key for advanced features."
        let input = NSSecureTextField(frame: NSRect(x: 0, y: 0, width: 320, height: 24))
        input.stringValue = licenseKey
        alert.accessoryView = input
        alert.addButton(withTitle: "Save")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn {
            licenseKey = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
            defaults.set(licenseKey, forKey: MenuConstants.licenseKeyStorageKey)
            if licenseKey.isEmpty {
                NSWorkspace.shared.open(URL(string: MenuConstants.pricingURL)!)
            }
        }
    }

    @objc private func toggleLaunchAtLogin(_ sender: NSMenuItem) {
        launchAtLoginEnabled.toggle()
        sender.state = launchAtLoginEnabled ? .on : .off
        configureLaunchAtLoginIfNeeded()
    }

    @objc private func toggleCrashReporting(_ sender: NSMenuItem) {
        crashReportingEnabled.toggle()
        sender.state = crashReportingEnabled ? .on : .off
        crashReporter.install(optedIn: crashReportingEnabled)
    }

    @objc private func openTUI() {
        do {
            _ = try uiLauncher.launch(target: .tui, ipcMode: .default)
        } catch {
            crashReporter.record(error: error, context: ["stage": "open_tui"])
        }
    }

    @objc private func openGradio() {
        do {
            _ = try uiLauncher.launch(target: .gradio, ipcMode: .default)
        } catch {
            crashReporter.record(error: error, context: ["stage": "open_gradio"])
        }
    }

    @objc private func checkForUpdates() {
        updateManager.checkForUpdates()
    }

    @objc private func quitApp() {
        NSApp.terminate(nil)
    }

    private func payloadWithLicense(_ payload: [String: JSONValue]) -> [String: JSONValue] {
        guard !licenseKey.isEmpty else { return payload }
        var updated = payload
        updated["license_key"] = .string(licenseKey)
        return updated
    }

    private func setStatusSubtitle(_ value: String) {
        statusItem.button?.toolTip = "Cloakroom: \(value)"
    }
}

private final class UpdateManager {
    func checkForUpdates() {
        // Sparkle integration point. This build keeps a safe fallback if Sparkle
        // is not linked in the current packaging profile.
        if let url = URL(string: "https://github.com/GreggBerretta/cloakroom/releases") {
            NSWorkspace.shared.open(url)
        }
    }
}

private final class LocalCrashReporter {
    private let queue = DispatchQueue(label: "cloakroom-crash-reporter")
    private var enabled = false

    func install(optedIn: Bool) {
        enabled = optedIn
        // Objective-C uncaught exception handlers require global C callbacks.
        // This wrapper keeps opt-in local reporting for handled failures.
    }

    func record(error: Error, context: [String: String]) {
        guard enabled else { return }
        let payload: [String: Any] = [
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "error_type": String(describing: type(of: error)),
            "message": sanitize(String(describing: error)),
            "context": context,
            "stack": sanitize(Thread.callStackSymbols.joined(separator: "\n")),
        ]
        write(payload: payload)
    }

    private func write(payload: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]) else {
            return
        }
        queue.async {
            let dir = URL(fileURLWithPath: NSHomeDirectory())
                .appendingPathComponent(".cloakroom")
                .appendingPathComponent("crash_reports")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let filename = "crash-\(Int(Date().timeIntervalSince1970)).json"
            let path = dir.appendingPathComponent(filename)
            try? data.write(to: path, options: [.atomic])
            try? FileManager.default.setAttributes(
                [.posixPermissions: 0o600],
                ofItemAtPath: path.path
            )
        }
    }

    private func sanitize(_ text: String) -> String {
        var value = text
        value = value.replacingOccurrences(
            of: #"\[[A-Z]+_\d{5}\]"#,
            with: "[REDACTED]",
            options: .regularExpression
        )
        value = value.replacingOccurrences(
            of: #"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"#,
            with: "[REDACTED]",
            options: [.regularExpression, .caseInsensitive]
        )
        return value
    }
}
