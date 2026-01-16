// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "WhisperMeet",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "WhisperMeet", targets: ["WhisperMeet"])
    ],
    targets: [
        .executableTarget(
            name: "WhisperMeet",
            path: "Sources"
        )
    ]
)
