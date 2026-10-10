
import AppIntents
import Foundation
import SwiftUI

enum ZEnum: String, AppEnum {
    case on, dash, quote, colon, hash, truthy, num, nully, lead, plain
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Zed"
    static let caseDisplayRepresentations: [ZEnum: DisplayRepresentation] = [
        .on: "On", .dash: "- dash", .quote: "it's", .colon: "a: b", .hash: "#tag",
        .truthy: "true", .num: "123", .nully: "null", .lead: " lead", .plain: "Plain words & more",
    ]
}
struct YEntity: AppEntity {
    var id: String
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Why Thing"
    static let defaultQuery = YQuery()
    var displayRepresentation: DisplayRepresentation { "x" }
}
struct YQuery: EntityQuery {
    func entities(for identifiers: [YEntity.ID]) async throws -> [YEntity] { [] }
    func suggestedEntities() async throws -> [YEntity] { [] }
}
struct XEntity: AppEntity {
    var id: String
    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Ex"
    static let defaultQuery = XQuery()
    var displayRepresentation: DisplayRepresentation { "x" }
}
struct XQuery: EntityQuery {
    func entities(for identifiers: [XEntity.ID]) async throws -> [XEntity] { [] }
}
struct AIntent: AppIntent {
    static let title: LocalizedStringResource = "Alpha: go"
    @Parameter(title: "Z") var z: ZEnum
    @Parameter(title: "Y") var y: YEntity
    @Parameter(title: "Text") var text: String
    func perform() async throws -> some IntentResult { .result() }
}
struct BIntent: AppIntent {
    static let title: LocalizedStringResource = "Beta"
    @Parameter(title: "X") var x: XEntity
    func perform() async throws -> some IntentResult { .result() }
}
struct CIntent: AppIntent {
    static let title: LocalizedStringResource = "Gamma"
    func perform() async throws -> some IntentResult { .result() }
}
struct Shortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: BIntent(), phrases: ["Beta \(.applicationName)"], shortTitle: "B", systemImageName: "b.circle")
        AppShortcut(intent: AIntent(), phrases: ["Open \(\.$z) in \(.applicationName)", "Alpha \(.applicationName) now", "\(.applicationName) alpha"], shortTitle: "A", systemImageName: "a.circle")
        AppShortcut(intent: CIntent(), phrases: ["Gamma \(.applicationName)"], shortTitle: "C", systemImageName: "c.circle")
    }
}
@main
struct ProbeApp: App { var body: some Scene { WindowGroup { Text("x") } } }
