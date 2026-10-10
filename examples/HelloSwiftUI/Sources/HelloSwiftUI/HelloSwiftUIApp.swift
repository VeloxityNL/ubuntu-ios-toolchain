import SwiftUI

@main
struct HelloSwiftUIApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}

struct ContentView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "swift")
                .font(.system(size: 48))
            Text("Hello from Ubuntu")
                .font(.title)
            Text("Built with the Ubuntu iOS Toolchain")
                .foregroundStyle(.secondary)
        }
        .padding()
    }
}
