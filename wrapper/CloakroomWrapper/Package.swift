// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CloakroomWrapper",
    platforms: [.macOS(.v13)],
    products: [
        .library(name: "CloakroomWrapper", targets: ["CloakroomWrapper"]),
        .executable(name: "wrapper-invariant-checks", targets: ["WrapperInvariantChecks"]),
        .executable(name: "cloakroom-menubar", targets: ["CloakroomMenuBar"]),
    ],
    targets: [
        .target(name: "CloakroomWrapper"),
        .executableTarget(
            name: "WrapperInvariantChecks",
            dependencies: ["CloakroomWrapper"]
        ),
        .executableTarget(
            name: "CloakroomMenuBar",
            dependencies: ["CloakroomWrapper"]
        ),
    ]
)
