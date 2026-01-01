// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TWRemindersListener",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "tw-reminders-listener",
            path: "Sources/TWRemindersListener"
        )
    ]
)
