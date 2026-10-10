# IceCubesApp with its 4 extensions in TestFlight, 2026-10-05

IceCubesApp (upstream 9efcb16) with all four app extensions (IceCubesNotifications,
IceCubesShareExtension, IceCubesActionExtension, IceCubesAppWidgetsExtensionExtension) and its
layered `AppIcon.icon` was built, signed and uploaded from the Linux chroot. App Store Connect
processed it to `VALID`. Nothing was submitted for review.

## App Store Connect records

- Bundle IDs, registered with the API key (`asc.bundle_id`):
  `com.joshuaswarren.omarchyappledev.icecubes` Z33J7BZC2R, `.IceCubesNotifications` 6XXUW25FL8,
  `.IceCubesShareExtension` A88XD3J5FZ, `.IceCubesActionExtension` JLM569Y7Q2,
  `.IceCubesAppWidgetsExtension` 643785X6N4.
- App Group `group.com.joshuaswarren.omarchyappledev.icecubes` (XFP3RK2TSY), created and assigned to
  all five IDs through the developer portal web session; `getAppIdDetail` lists the group on each.
- App record 6819399771 ("Omarchy IceCubes Test"), created with `POST /iris/v1/apps` (201).

## Build and upload

```
$ BUNDLE_ID=com.joshuaswarren.omarchyappledev.icecubes compat/icecubes/setup.sh ~/ice-ship-1929
$ APP_ICON=AppIcon APP_GROUPS=group.com.joshuaswarren.omarchyappledev.icecubes ship.sh --upload
stamped com.joshuaswarren.omarchyappledev.icecubes 1.0.0 (202610051936), iphoneos27.0 24A430, Xcode 27.0 27A266a, Mach-O sdk 27.0 in 5 file(s)
identity for 9LX44YXXVX.com.joshuaswarren.omarchyappledev.icecubes: profile b65c2491-f97c-41a1-8b9a-0b801c664472, expires 2027-10-04
(+ one App Store profile per extension)
99/99 checks passed
uploaded 46225334 bytes in 9 part(s)
buildUpload 157008db-cb6b-4cc5-b0e0-ec428ba1d12c: COMPLETE
$ asc-builds.sh 6819399771
157008db-cb6b-4cc5-b0e0-ec428ba1d12c 202610051936 VALID 2026-10-05T12:39:24-07:00 False 18.5 APP_STORE_ELIGIBLE
```

## Still left out (warnings, not errors)

- Alternate icons (`AppIconAlternate*.appiconset`, `AlternateIcons/*.icon`) and the extensions'
  own icon sets: the Linux actool compiles only the `--app-icon` set.
- `avatar.imageset` (HEIC).
- App Intents metadata (`Metadata.appintents`): no Linux processor yet.
- `UserPreferences.sharedDefault` names upstream's group `group.com.thomasricouard.IceCubesApp`;
  the build is signed with ours, so the shared defaults suite is not shared at run time.
