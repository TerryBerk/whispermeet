import SwiftUI

struct MenuBarView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("WhisperMeet")
                .font(.headline)

            Divider()

            Button("Start Manual Recording") {
                // TODO: Implement
            }

            Divider()

            Text("Recent Transcripts")
                .font(.subheadline)
                .foregroundColor(.secondary)

            Text("No recordings yet")
                .foregroundColor(.secondary)
                .padding(.vertical, 8)

            Divider()

            HStack {
                Button("Settings") {
                    NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
                }
                Spacer()
                Button("Quit") {
                    NSApplication.shared.terminate(nil)
                }
            }
        }
        .padding()
        .frame(width: 280)
    }
}

struct SettingsView: View {
    var body: some View {
        Text("Settings")
            .frame(width: 400, height: 300)
    }
}
