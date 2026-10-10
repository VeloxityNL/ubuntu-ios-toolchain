import AppIntents
import SwiftUI

struct PingIntent: AppIntent {
    static var title: LocalizedStringResource = "Ping"
    func perform() async throws -> some IntentResult { .result() }
}

struct PingShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: PingIntent(), phrases: ["Ping with \(.applicationName)"])
    }
}

@main
struct IntentFixture: App {
    var body: some Scene { WindowGroup { Text("Fixture") } }
}
