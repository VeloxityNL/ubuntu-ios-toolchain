// Linux adapter: Swift replacements for the target's ObjC-only category members
// (ObjC sources do not build on Linux; the bridging header is inert).
// Same API and semantics as Mac/NSOpenPanel+Extras.m and Mac/WKPreferencesPrivate.h.

import ObjectiveC
import WebKit

extension NSOpenPanel {
	// https://github.com/Ranchero-Software/NetNewsWire/issues/4840
	// The deprecated allowedFileTypes is deliberate: the OPML UTI is not
	// reliable, so pin the file extensions.
	func acceptOPML() {
		allowedFileTypes = ["opml", "xml"]
	}
}

nonisolated(unsafe) private var developerExtrasKey: UInt8 = 0

extension WKPreferences {
	// Private WebKit property; the Darwin SDK hides it. Store the flag on the
	// object so get/set round-trip (the WebKit-internal effect is not wired).
	var _developerExtrasEnabled: Bool {
		get { objc_getAssociatedObject(self, &developerExtrasKey) as? Bool ?? false }
		set { objc_setAssociatedObject(self, &developerExtrasKey, newValue, .OBJC_ASSOCIATION_RETAIN) }
	}
}
