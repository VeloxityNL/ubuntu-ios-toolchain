# One packed atlas per scale, sized to process — TestFlight, 2026-10-06/07

AssetKit wrote one `ZZZZPackedAsset` per symbol set, all under the same rendition
key (element 9, part 181, identifier 0). App Store processing resolves that key
to the first rendition in the car, so the sorted walk of 98ff033 could put a
narrower atlas first and leave every other set's cached sprite out of bounds
(upload f3a1784f stayed PROCESSING; FINDINGS.md 54).

## Apple probe (actool 27.0, Xcode 27.0 27A266a on macstudio)

`actool-oracle.sh` compiled the same catalogs Apple-side. One atlas per scale
for the whole catalog, never per set:

| catalog | symbol sets | PackedImage rows |
|---|---|---|
| IceCubesApp `Assets.xcassets` | 2 (Rocket, Rocket.Fill) | 3: `ZZZZPackedAsset-{1,2,3}.0.1-gamut0` 62x44 / 116x82 / 170x120 |
| NNW `two.xcassets` (2 sets) | 2 | 3: 84x62 / 118x124 / 172x184 |
| NNW app catalog (1 set, prior probe) | 1 | 3: 60x34 / 112x64 / 164x94 |

Keys of every atlas: element 9, part 181, identifier 0, glyphWeight 0,
glyphSize 0, scale 1/2/3, deploymentTarget 5, idiom universal. Cached
renditions: element 85, part 181, glyphWeight 4, glyphSize 2, dimension2 =
cached index 0..2, per-set identifier; each links its atlas through the 1010
INLK TVL (key pairs element 9, part 181, scale, deploymentTarget 5). Cached
CSI is 334 bytes on both sides with the same TVL chain (1001/1003/1010/1004).

Apple's packer is multi-row (IceCubes 1x: six sprites in two shelves, 62x44)
and reserves spare height; its atlases stay small because its cached sprites
are small (15x16 at 1x) while AssetKit's template-bbox sprites are 199x110
(pre-existing; the VALID 9f509fe car carried the same). Placement is not what
gates processing — dbad43f2 went VALID with AssetKit's own placements.

## AssetKit change

Branch `omarchy/atlas-per-scale` on joshuaswarren/AssetKit, final revision
`6b10c19e62a335b8c33ce7e1abb140da45ca9bdb` (branch of the pin 9f509fe via
98ff033, whose sorted byte-stable walk is kept). `SymbolRenderer` prepares
every `.symbolset` first and emits ONE `ZZZZPackedAsset` per scale across all
sets; shelves wrap at 2048 px (max-row-width reported as atlas width, index
tie-break for determinism).

- AssetKit test suite: 72/72 pass (two runs: bece8b6 and 6b10c19).
- `two.xcassets` oracle compare: 25 rows both sides, 22 common; only the 3
  atlas rows' PixelWidth/Height differ (ours 121x34/228x64/334x94 pre-wrap).
- IceCubes car check: 3 atlases, keys unique, all 18 cached links resolve,
  no sprite out of bounds, no overlap.

## The stall that taught the size limit

Upload `eb830d06-a369-4ef2-a094-2b8aad11c1c0` (build 202610062021, merged
atlases, SINGLE SHELF → 1496x150/2976x296/4454x442): PROCESSING for 10+
hours. Same-night control — identical catalog, actool rebuilt at 9f509fe —
upload `065dc987-37ab-4ed8-9825-04b7e0eefc37` (build 202610070209): COMPLETE
within minutes. Historical VALID envelope for any car in this program: max
atlas dimension 2078 (the per-set IceCubes atlases). The only structural
outlier of the stalled car was the 4454 px shelf. Conclusion: shelves wrap at
2048 px; fixed in `6b10c19` ("Packed atlas width must cover the widest shelf"
+ "Wrap packed-atlas shelves at 2048 px"). IceCubes' atlases become
1496x150 / 1664x546 / 1713x1187; NNW single-set stays byte-identical
(60x34/112x64/164x94 — no wrap triggered, same placements as Apple's).

## TestFlight (final revision 6b10c19)

| app | upload | build | state |
|---|---|---|---|
| NetNewsWire 6819098049 | c06a0480-88c8-41eb-b147-5321c8174b20 | 202610070306 | VALID |
| Mastodon 6819300325 | 1216a4f5-6baa-4c80-98b7-ed2763bc923f | 202610070316 | VALID |
| IceCubes 6819399771 | fb2771bf-1101-45d1-9876-298b7ede9bd8 | 202610070230 | PROCESSING >90 min (all prior VALID windows passed) |

Ship checks: NNW 86/86, Mastodon 118/118, IceCubes 102/102. NNW's shipped car
carries Apple-identical atlas dims; Mastodon has no symbol sets (no atlases).

## Final outcome: pin stays at 9f509fe

Three merged-atlas variants of the same IceCubes catalog all stalled; the
9f509fe per-set control went COMPLETE in minutes. Per acceptance, the pin
is not bumped; main 6f9116f holds it on 9f509fe.

| upload | AssetKit | IceCubes atlas layout | result |
|---|---|---|---|
| eb830d06 (202610062021) | bece8b6 | merged, single shelf 1496x150/2976x296/**4454x442** | PROCESSING 10+ h |
| 065dc987 (202610070209) | 9f509fe (control) | per-set, larger first, max dim 2078 | COMPLETE in minutes |
| fb2771bf (202610070230) | 6b10c19 (wrap) | merged, wrapped 1496x150/1664x546/1713x1187 | PROCESSING ~3 h |
| 0062c26c (202610070533) | d9a83f77 (wrap + atlas-first) | as fb2771bf, atlas first per scale | PROCESSING ~70 min |

NetNewsWire 202610070306 (c06a0480) and Mastodon 202610070316 (1216a4f5)
are VALID on 6b10c19; neither exercises the merged multi-set atlas (NNW
does not wrap, Mastodon has no symbol sets). Every car that ever processed
had max atlas dimension 2078; the 4454 px single shelf of eb830d06 was
the one measured outlier — but the wrapped (1713) and atlas-first
variants still stall past every historical VALID window, isolating the
per-scale merge as the remaining difference against the per-set 9f509fe
control. Apple's own oracle emits per-scale, so the layout is in
principle processable; the catalog in this program passes only with
per-set atlases.

## Final test inventory

- 9f509fe: control VALID (065dc987), interim VALIDs (NetNewsWire 8443f8d0
  on 6b10c19 variant, Mastodon c598be6d on 6b10c19 variant), plus prior
  history (54834467, dbad43f2). Shipped the `d9a83f77` order variant
  (0062c26c) from the in-chroot actool that is left installed.
- NNW 202610070306 VALID (6b10c19). Mastodon 202610070316 VALID (6b10c19).
- All three background watcher jobs and the order-variant ship have
  settled; no further action from this agent — handoff in the final yield.
