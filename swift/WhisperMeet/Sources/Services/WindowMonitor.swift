import Cocoa
import Combine

class WindowMonitor: ObservableObject {
    @Published var detectedMeeting: DetectedMeeting?
    @Published var isMonitoring = false

    private var timer: Timer?
    private var config: AppConfig

    struct DetectedMeeting {
        let app: MonitoredApp
        let windowTitle: String
        let timestamp: Date
    }

    init(config: AppConfig = .default) {
        self.config = config
    }

    func startMonitoring() {
        isMonitoring = true
        timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.checkForMeetings()
        }
    }

    func stopMonitoring() {
        isMonitoring = false
        timer?.invalidate()
        timer = nil
    }

    private func checkForMeetings() {
        let runningApps = NSWorkspace.shared.runningApplications

        for monitoredApp in config.apps {
            guard let app = runningApps.first(where: { $0.bundleIdentifier == monitoredApp.bundleId }) else {
                continue
            }

            if let windowTitle = getActiveWindowTitle(for: app),
               matchesPattern(windowTitle, patterns: monitoredApp.windowPatterns) {
                let meeting = DetectedMeeting(
                    app: monitoredApp,
                    windowTitle: windowTitle,
                    timestamp: Date()
                )

                DispatchQueue.main.async {
                    self.detectedMeeting = meeting
                }
                return
            }
        }
    }

    private func getActiveWindowTitle(for app: NSRunningApplication) -> String? {
        let appElement = AXUIElementCreateApplication(app.processIdentifier)

        var windowsRef: CFTypeRef?
        let result = AXUIElementCopyAttributeValue(appElement, kAXWindowsAttribute as CFString, &windowsRef)

        guard result == .success,
              let windows = windowsRef as? [AXUIElement],
              let firstWindow = windows.first else {
            return nil
        }

        var titleRef: CFTypeRef?
        AXUIElementCopyAttributeValue(firstWindow, kAXTitleAttribute as CFString, &titleRef)

        return titleRef as? String
    }

    private func matchesPattern(_ title: String, patterns: [String]) -> Bool {
        let lowercasedTitle = title.lowercased()
        return patterns.contains { lowercasedTitle.contains($0.lowercased()) }
    }
}
