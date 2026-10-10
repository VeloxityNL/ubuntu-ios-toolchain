import Foundation

/// Generated asset symbols (ColorResource / ImageResource), in the text actool 27.0 writes.
enum AssetSymbols {
    struct Asset {
        var name: String
        var relativePath: String
        var isColor: Bool
        var catalogPath: String
    }

    static func collect(catalog: URL) throws -> [Asset] {
        var found: [Asset] = []
        func walk(_ dir: URL, prefix: String, relative: String) throws {
            let children = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
            for child in children.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
                let base = child.deletingPathExtension().lastPathComponent
                let rel = "\(relative)/\(child.lastPathComponent)"
                switch child.pathExtension {
                case "colorset":
                    found.append(Asset(name: prefix + base, relativePath: rel, isColor: true, catalogPath: catalog.path))
                case "imageset":
                    found.append(Asset(name: prefix + base, relativePath: rel, isColor: false, catalogPath: catalog.path))
                case "":
                    guard child.hasDirectoryPath || (try? child.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
                    else { continue }
                    try walk(child, prefix: prefix + (providesNamespace(child) ? base + "/" : ""), relative: rel)
                default: continue
                }
            }
        }
        try walk(catalog, prefix: "", relative: ".")
        return found
    }

    static func providesNamespace(_ folder: URL) -> Bool {
        guard let data = try? Data(contentsOf: folder.appendingPathComponent("Contents.json")),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let properties = json["properties"] as? [String: Any] else { return false }
        return properties["provides-namespace"] as? Bool ?? false
    }

    static func words(_ name: String) -> [String] {
        name.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
    }

    /// "Dot" -> "dot", "brand-blue" -> "brandBlue", "URL" -> "url".
    static func swiftName(_ name: String) -> String {
        let parts = words(name)
        guard let first = parts.first else { return "_" }
        let head = first == first.uppercased() ? first.lowercased() : first.prefix(1).lowercased() + first.dropFirst()
        let name = head + parts.dropFirst().map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined()
        return name.first?.isNumber == true ? "_" + name : name
    }

    /// "Dot" -> "Dot", "brand-blue" -> "BrandBlue".
    static func objcName(_ name: String) -> String {
        words(name).map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined()
    }

    static func swift(_ assets: [Asset]) -> String {
        var out = """
        import Foundation
        #if canImport(DeveloperToolsSupport)
        import DeveloperToolsSupport
        #endif

        #if SWIFT_PACKAGE
        private let resourceBundle = Foundation.Bundle.module
        #else
        private class ResourceBundleClass {}
        private let resourceBundle = Foundation.Bundle(for: ResourceBundleClass.self)
        #endif


        """
        for (isColor, kind, mark) in [(true, "ColorResource", "Color"), (false, "ImageResource", "Image")] {
            let group = assets.filter { $0.isColor == isColor }
            guard !group.isEmpty else { continue }
            out += "// MARK: - \(mark) Symbols -\n\n"
            out += "@available(iOS 17.0, macOS 14.0, tvOS 17.0, watchOS 10.0, *)\n"
            out += "extension DeveloperToolsSupport.\(kind) {\n\n"
            for asset in group {
                let what = isColor ? "color" : "image"
                out += "    /// The \"\(asset.name)\" asset catalog \(what) resource.\n"
                out += "    static let \(swiftName(asset.name)) = DeveloperToolsSupport.\(kind)"
                out += "(name: \"\(asset.name)\", bundle: resourceBundle)\n\n"
            }
            out += "}\n\n"
        }
        return out
    }

    static func objc(_ assets: [Asset], bundleID: String) -> String {
        var out = """
        #import <Foundation/Foundation.h>

        #if __has_attribute(swift_private)
        #define AC_SWIFT_PRIVATE __attribute__((swift_private))
        #else
        #define AC_SWIFT_PRIVATE
        #endif

        /// The resource bundle ID.
        static NSString * const ACBundleID AC_SWIFT_PRIVATE = @"\(bundleID)";


        """
        for asset in assets.filter(\.isColor) + assets.filter({ !$0.isColor }) {
            let (what, prefix) = asset.isColor ? ("color", "ACColorName") : ("image", "ACImageName")
            out += "/// The \"\(asset.name)\" asset catalog \(what) resource.\n"
            out += "static NSString * const \(prefix)\(objcName(asset.name)) AC_SWIFT_PRIVATE = @\"\(asset.name)\";\n\n"
        }
        return out + "#undef AC_SWIFT_PRIVATE\n"
    }

    static func index(_ assets: [Asset]) throws -> Data {
        func entries(_ isColor: Bool) -> [[String: String]] {
            assets.filter { $0.isColor == isColor }.map {
                ["catalogPath": $0.catalogPath, "relativePath": $0.relativePath, "swiftSymbol": swiftName($0.name),
                 "objcSymbol": (isColor ? "ACColorName" : "ACImageName") + objcName($0.name)]
            }
        }
        let plist: [String: Any] = ["colors": entries(true), "images": entries(false), "symbols": [Any]()]
        return try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
    }
}
