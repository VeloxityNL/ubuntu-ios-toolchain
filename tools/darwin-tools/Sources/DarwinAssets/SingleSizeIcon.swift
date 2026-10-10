import AssetKit
import Foundation
import PNG

// Xcode 14+ app icons are one 1024 pt "universal" image with no scale; actool
// derives everything from it. AssetKit keys renditions per idiom and per
// appearance, so rewrite that form into the exact shape Apple's actool
// compiles for it (verified against Apple's actool 27.0 output for the NNW
// catalog, oracle/nnwcar/apple, and the IceCubes alternate-icon oracle):
//
// - one 1024x1024 1x entry per target device and appearance variant
//   (default, dark, tinted), source filenames kept: actool stores them in
//   the CSI name field,
// - loose <Name>60x60@2x.png (120 px) and <Name>76x76@2x~ipad.png (152 px)
//   downsamples for the primary icon only, as Apple writes for this form
//   (alternate icons get no loose files),
// - an AppIconBundle with Apple's partial-plist shape for the primary.
//
// Every single-size .appiconset in the catalog is expanded — the primary and
// the alternate sets (actool --alternate-app-icon / --include-all-app-icons)
// share the form. Classic appiconsets that list every size are left untouched
// (the classic multi-rendition car is what those apps have always shipped).
public enum SingleSizeIcon {
    /// Returns `catalog` itself, or an expanded copy under a temporary
    /// directory when it contains single-size appiconsets, plus the primary
    /// icon's bundle (`--app-icon` name) or nil. `idioms` are actool's
    /// `--target-device` values.
    public static func expandIfNeeded(catalog: URL, appIcon: String?, idioms: [String]) throws -> (URL, AppIconBundle?) {
        let fm = FileManager.default
        var single: [(set: URL, images: [[String: Any]], base: String)] = []
        for iconSet in try fm.contentsOfDirectory(at: catalog, includingPropertiesForKeys: nil)
        where iconSet.pathExtension == "appiconset" {
            let contentsURL = iconSet.appendingPathComponent("Contents.json")
            guard let contents = try JSONSerialization.jsonObject(with: Data(contentsOf: contentsURL)) as? [String: Any],
                  let images = contents["images"] as? [[String: Any]],
                  !images.isEmpty,
                  images.allSatisfy({
                      $0["idiom"] as? String == "universal"
                          && $0["scale"] == nil
                          && $0["size"] as? String == "1024x1024"
                  }),
                  let base = images.first(where: { $0["appearances"] == nil }),
                  let baseFilename = base["filename"] as? String
            else { continue }
            // An empty single-size set (no filename entries anywhere) is an
            // Xcode placeholder: Apple compiles it to nothing, silently.
            guard images.contains(where: { $0["filename"] != nil }) else { continue }
            single.append((iconSet, images, baseFilename))
        }
        guard !single.isEmpty else { return (catalog, nil) }

        // Copy the merged catalog once, replacing every single-size set.
        let work = fm.temporaryDirectory.appendingPathComponent("xcassets-\(UUID().uuidString)")
        let expanded = work.appendingPathComponent(catalog.lastPathComponent)
        try fm.copyItem(at: catalog, to: expanded)

        var primaryBundle: AppIconBundle?
        for item in single {
            let setName = item.set.deletingPathExtension().lastPathComponent
            let outSet = expanded.appendingPathComponent(item.set.lastPathComponent)
            // Entries matching Apple's compiled shape: every variant keyed once
            // per target idiom, source filename preserved (actool puts it in the
            // CSI name field; assetutil surfaces it as RenditionName).
            let entries: [[String: Any]] = idioms.flatMap { idiom in
                item.images.filter { $0["filename"] != nil }.map { image in
                    image.merging(["idiom": idiom, "scale": "1x"]) { $1 }
                }
            }
            let newContents: [String: Any] = [
                "images": entries,
                "info": ["author": "xcode", "version": 1],
            ]
            try JSONSerialization.data(withJSONObject: newContents, options: [.prettyPrinted, .sortedKeys])
                .write(to: outSet.appendingPathComponent("Contents.json"))
            if setName == appIcon {
                primaryBundle = try primaryAppIconBundle(
                    set: outSet, name: setName,
                    images: item.images, baseFilename: item.base, idioms: idioms)
            }
        }
        return (expanded, primaryBundle)
    }

    /// The primary icon's loose downsamples and partial-plist glue.
    private static func primaryAppIconBundle(
        set: URL, name: String,
        images: [[String: Any]], baseFilename: String, idioms: [String]
    ) throws -> AppIconBundle {
        let sourceURL = set.appendingPathComponent(baseFilename)
        let decoded = try PNGSource.decodeBGRA(Data(contentsOf: sourceURL))
        let pixels = straightRGBA(premultipliedBGRA: decoded.bgra8)

        // Loose PNGs Apple writes for this form: the home-screen sizes.
        var loose: [LooseFile] = []
        let looseSpecs: [(points: Double, scale: Int, file: String)] = [
            (60, 2, "\(name)60x60@2x.png"), (76, 2, "\(name)76x76@2x~ipad.png"),
        ]
        for spec in looseSpecs {
            let side = Int((spec.points * Double(spec.scale)).rounded())
            let down = downsampleRGBA(pixels, from: Int(decoded.width), to: side)
            let image = PNG.Image(
                packing: down, size: (side, side),
                layout: .init(format: .rgba8(palette: [], fill: nil)))
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("icon-\(UUID().uuidString)-\(spec.file)")
            try image.compress(path: file.path, level: 9)
            let data = try Data(contentsOf: file)
            loose.append(LooseFile(name: spec.file, data: data))
        }

        let primary: [String: any Sendable] = [
            "CFBundlePrimaryIcon": [
                "CFBundleIconFiles": ["\(name)60x60"],
                "CFBundleIconName": name,
            ] as [String: any Sendable],
        ]
        var additions: [String: any Sendable] = ["CFBundleIcons": primary]
        var ipad: [String: any Sendable] = ["CFBundleIconFiles": ["\(name)60x60", "\(name)76x76"]]
        if idioms.contains("ipad") { ipad["CFBundleIconName"] = name }
        additions["CFBundleIcons~ipad"] = ["CFBundlePrimaryIcon": ipad] as [String: any Sendable]
        return AppIconBundle(
            primaryIconName: name,
            infoPlistAdditions: additions,
            looseFiles: loose)
    }

    /// Un-premultiplies 8-bit BGRA pixels into straight RGBA for the
    /// alpha-preserving downsampler.
    static func straightRGBA(premultipliedBGRA: [UInt8]) -> [PNG.RGBA<UInt8>] {
        var out: [PNG.RGBA<UInt8>] = []
        out.reserveCapacity(premultipliedBGRA.count / 4)
        var i = 0
        while i < premultipliedBGRA.count {
            let b = premultipliedBGRA[i], g = premultipliedBGRA[i + 1]
            let r = premultipliedBGRA[i + 2], a = premultipliedBGRA[i + 3]
            let alpha = Int(a)
            let unpre: (Int) -> UInt8 = { channel in
                alpha == 0 ? 0 : UInt8(min(255, channel * 255 / alpha))
            }
            out.append(PNG.RGBA(unpre(Int(r)), unpre(Int(g)), unpre(Int(b)), a))
            i += 4
        }
        return out
    }

    /// Area-average downsample of a square RGBA image, preserving alpha
    /// (premultiplied accumulate, then un-premultiply per target pixel).
    static func downsampleRGBA(
        _ src: [PNG.RGBA<UInt8>], from n: Int, to m: Int
    ) -> [PNG.RGBA<UInt8>] {
        var out: [PNG.RGBA<UInt8>] = []
        out.reserveCapacity(m * m)
        for y in 0..<m {
            let y0 = y * n / m, y1 = max(y0 + 1, (y + 1) * n / m)
            for x in 0..<m {
                let x0 = x * n / m, x1 = max(x0 + 1, (x + 1) * n / m)
                var r = 0, g = 0, b = 0, a = 0, count = 0
                for sy in y0..<y1 {
                    for sx in x0..<x1 {
                        let p = src[sy * n + sx], alpha = Int(p.a)
                        r += Int(p.r) * alpha; g += Int(p.g) * alpha; b += Int(p.b) * alpha
                        a += alpha; count += 1
                    }
                }
                let outAlpha = a / count
                let unpre: (Int) -> UInt8 = { channel in
                    outAlpha == 0 ? 0 : UInt8(min(255, (channel / count) * 255 / outAlpha))
                }
                out.append(PNG.RGBA(unpre(r), unpre(g), unpre(b), UInt8(outAlpha)))
            }
        }
        return out
    }
}
