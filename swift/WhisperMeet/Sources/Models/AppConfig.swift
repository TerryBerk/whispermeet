import Foundation

struct MonitoredApp: Codable, Identifiable {
    var id: String { bundleId }
    let name: String
    let bundleId: String
    let windowPatterns: [String]
    var autoStart: AutoStartMode

    enum AutoStartMode: String, Codable {
        case auto = "true"
        case prompt = "prompt"
        case disabled = "false"
    }
}

struct AppConfig: Codable {
    var apps: [MonitoredApp]

    static let `default` = AppConfig(apps: [
        MonitoredApp(
            name: "Zoom",
            bundleId: "us.zoom.xos",
            windowPatterns: ["Zoom Meeting", "Zoom Webinar"],
            autoStart: .prompt
        ),
        MonitoredApp(
            name: "Telegram",
            bundleId: "ru.keepcoder.Telegram",
            windowPatterns: ["Voice Chat", "Video Chat"],
            autoStart: .prompt
        ),
        MonitoredApp(
            name: "Telemost (Arc)",
            bundleId: "company.thebrowser.Browser",
            windowPatterns: ["Telemost", "telemost.yandex"],
            autoStart: .prompt
        )
    ])
}
