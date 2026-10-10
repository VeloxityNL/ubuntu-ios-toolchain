# Swift macro expansions on Linux vs Xcode 27.0, 2026-10-06

Every Apple macro that IceCubesApp, NetNewsWire and Mastodon use expands on Linux to the same code
as Xcode 27.0 (swiftc 6.4.0.34.1). Ten probe files were compiled with the same flags on both sides
(`-target arm64-apple-ios18.0 -DDEBUG -Xfrontend -enable-cross-import-overlays
-Xfrontend -dump-macro-expansions`); Linux used the real build's plugin wiring (SDK plugin stubs routed
to OpenAppleMacrosServer, then the toolchain's swift-plugin-server).

| Probe | Macros | Expansion |
|---|---|---|
| p1, p8 | `@Observable`, `@ObservationTracked`, `@ObservationIgnored` | identical |
| p2, p5 | `@Model` (with its helpers), IceCubes' `TagGroup` model | identical |
| p3 | `#Predicate` | identical |
| p6 | `@Query` with sort key path and order, `#Predicate` | identical |
| p9 | `@Entry` (SwiftUI; used 15 times by IceCubes' ButtonKit dependency) | identical |
| p10 | `@Test`, `@Suite`, `#expect` | identical |
| p4, p7 | `#Preview`, plain and named | identical except the indent of one closure line (2 spaces) |

The `#Preview` indent difference is whitespace inside a closure body and does not change the
compiled code. Use counts in the three apps: `@Observable` and its helpers 92, `#Preview` 66,
`@Query` 15, `@Entry` 15, `#Predicate` 6, `@Model` 5. None of the apps' 62 package dependencies
declares its own macro. Builds that use all of them are VALID in TestFlight, for example
IceCubesApp 202610060246.

Probes: `~/tmp/apple-dev/MacroParity/` (oracle runner and Xcode outputs) and the chroot's
`/home/builder/MacroParity/` (sources and Linux outputs).
