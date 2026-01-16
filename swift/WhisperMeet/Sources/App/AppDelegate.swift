import Cocoa
import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem?
    var popover: NSPopover?

    func applicationDidFinishLaunching(_ notification: Notification) {
        setupMenuBar()
        startBackendServer()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopBackendServer()
    }

    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem?.button {
            button.image = NSImage(systemSymbolName: "mic.circle", accessibilityDescription: "WhisperMeet")
            button.action = #selector(togglePopover)
        }

        popover = NSPopover()
        popover?.contentSize = NSSize(width: 300, height: 400)
        popover?.behavior = .transient
        popover?.contentViewController = NSHostingController(rootView: MenuBarView())
    }

    @objc func togglePopover() {
        if let button = statusItem?.button {
            if popover?.isShown == true {
                popover?.performClose(nil)
            } else {
                popover?.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            }
        }
    }

    // MARK: - Backend Server Management

    private func startBackendServer() {
        Task {
            do {
                try await BackendClient.shared.startServer()
                print("Backend server started successfully")
            } catch {
                print("Failed to start backend server: \(error)")
                // Show alert to user
                await MainActor.run {
                    let alert = NSAlert()
                    alert.messageText = "Backend Server Error"
                    alert.informativeText = error.localizedDescription
                    alert.alertStyle = .warning
                    alert.addButton(withTitle: "OK")
                    alert.runModal()
                }
            }
        }
    }

    private func stopBackendServer() {
        Task {
            await BackendClient.shared.stopServer()
            print("Backend server stopped")
        }
    }
}
