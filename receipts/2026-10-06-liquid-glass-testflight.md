# Liquid Glass pre-render on Linux, in TestFlight, 2026-10-06

The Linux `actool` (AssetKit 3177a3e, pinned in `tools/darwin-tools/Package.swift`) renders the baked
light, dark and tinted images of an Icon Composer `.icon` the way Apple's IconRendering does. The steps
were recorded from IconRendering's display lists on macstudio: the P3 background gradient, plus-darker
group shadows (blur 22.4, offset 16,16), the translucency mask, glow, two glass highlight passes, the
chiclet rim strokes and the border.

## Pixel comparison with actool 27.0

Mean / max absolute difference per 8-bit channel against Apple's baked image (actool 27.0 is
deterministic: three runs gave identical pre-renders).

| Icon | Light | Dark | Tinted |
|---|---|---|---|
| IceCubesApp AppIcon | 1.049 / 39 | 1.481 / 59 | 1.165 / 79 |
| AppIconAlternate1 (held out) | 1.856 / 56 | 1.902 / 85 | 1.272 / 79 |
| AppIconAlternate2 (held out) | 2.861 / 116 | 2.711 / 108 | 2.653 / 113 |
| AppIconAlternate46 (held out) | 1.950 / 147 | 1.499 / 161 | 2.259 / 117 |

Before this work, IceCubes was 8.5 / 10.3 / 12.6. The rest is at shape edges inside IconRendering's
single compositing render. Ruled out by measurement: the layer resampling filter, an anti-aliased
distance transform, supersampled coverage, and 10-bit quantization of the distance field (captured from
RenderBox: a Euclidean field, RGB10A2Unorm). No per-icon tables are used.

IceCubes, own build of `actool` from the pin:

```
$ python3 glass-lab/lab.py prerender vs oracle/icecubes-apple/out-direct
light mean 1.049 max 39 / dark mean 1.481 max 59 / tinted mean 1.165 max 79
partial.plist equal: True
$ assetutil-compare.sh  (Apple assetutil, 15 fields)
rows apple=30 ours=30 common=30
```

## TestFlight

IceCubesApp with its 4 extensions, App Intents metadata and the new renderer:

```
101/101 checks passed
buildUpload 9cb09967-9cea-425b-9585-5314a520c041: COMPLETE
$ asc-builds.sh 6819399771
9cb09967-9cea-425b-9585-5314a520c041 202610060039 VALID 2026-10-05T17:41:45-07:00 False 18.5 APP_STORE_ELIGIBLE
```

Regression with the pin: template, branch and dynamic products build; demo 37/37, iPad demo 38/38,
IceCubesApp 101/101, NetNewsWire 85/85.
