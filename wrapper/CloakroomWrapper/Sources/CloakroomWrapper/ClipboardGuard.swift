import Foundation

public protocol ClipboardStore: AnyObject {
    var changeCount: Int { get }
    func readString() -> String?
    func writeString(_ value: String) throws
}

public enum ClipboardGuardError: Error, Equatable {
    case clipboardEmpty
    case changeCountNotIncremented(step: String)
}

public final class ZeroingBuffer {
    private var bytes: [UInt8]

    public init(_ string: String) {
        self.bytes = Array(string.utf8)
    }

    public func value() -> String {
        String(decoding: bytes, as: UTF8.self)
    }

    public func wipe() {
        for index in bytes.indices {
            bytes[index] = 0
        }
    }
}

public final class ClipboardGuard {
    private let store: ClipboardStore
    private let placeholder: String

    public init(store: ClipboardStore, placeholder: String = "[CLOAKROOM_CLIPBOARD_CLEARED]") {
        self.store = store
        self.placeholder = placeholder
    }

    public func anonymize(
        engineTransform: (String) throws -> String
    ) throws -> String {
        guard let plaintext = store.readString(), !plaintext.isEmpty else {
            throw ClipboardGuardError.clipboardEmpty
        }

        let buffer = ZeroingBuffer(plaintext)
        defer { buffer.wipe() }

        let beforeClear = store.changeCount
        try store.writeString(placeholder)
        guard store.changeCount > beforeClear else {
            throw ClipboardGuardError.changeCountNotIncremented(step: "placeholder_clear")
        }

        let tokenized = try engineTransform(buffer.value())

        let beforeTokenWrite = store.changeCount
        try store.writeString(tokenized)
        guard store.changeCount > beforeTokenWrite else {
            throw ClipboardGuardError.changeCountNotIncremented(step: "token_write")
        }

        return tokenized
    }

    public func restore(
        engineTransform: (String) throws -> String
    ) throws -> String {
        guard let tokenized = store.readString(), !tokenized.isEmpty else {
            throw ClipboardGuardError.clipboardEmpty
        }

        let inputBuffer = ZeroingBuffer(tokenized)
        defer { inputBuffer.wipe() }

        let beforeClear = store.changeCount
        try store.writeString(placeholder)
        guard store.changeCount > beforeClear else {
            throw ClipboardGuardError.changeCountNotIncremented(step: "placeholder_clear")
        }

        let restoredText = try engineTransform(inputBuffer.value())

        let outputBuffer = ZeroingBuffer(restoredText)
        defer { outputBuffer.wipe() }

        let beforeRestoreWrite = store.changeCount
        try store.writeString(outputBuffer.value())
        guard store.changeCount > beforeRestoreWrite else {
            throw ClipboardGuardError.changeCountNotIncremented(step: "restore_write")
        }

        return restoredText
    }

    @discardableResult
    public func scrubOnLaunchIfContains(signature: String) throws -> Bool {
        guard let current = store.readString() else {
            return false
        }
        guard current.contains(signature) else {
            return false
        }

        let before = store.changeCount
        try store.writeString(placeholder)
        guard store.changeCount > before else {
            throw ClipboardGuardError.changeCountNotIncremented(step: "launch_scrub")
        }
        return true
    }
}
