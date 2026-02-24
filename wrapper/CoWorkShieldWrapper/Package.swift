// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CoWorkShieldWrapper",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "CoWorkShieldWrapper", targets: ["CoWorkShieldWrapper"]),
        .executable(name: "wrapper-invariant-checks", targets: ["WrapperInvariantChecks"]),
        .executable(name: "cowork-shield-menubar", targets: ["CoWorkShieldMenuBar"]),
    ],
    targets: [
        .target(name: "CoWorkShieldWrapper"),
        .executableTarget(
            name: "WrapperInvariantChecks",
            dependencies: ["CoWorkShieldWrapper"]
        ),
        .executableTarget(
            name: "CoWorkShieldMenuBar",
            dependencies: ["CoWorkShieldWrapper"]
        ),
    ]
)
