CardForge 4D 0.7 Preview

This release removes HueForge from the face production path. CardForge creates a direct Bambu Studio multipart 3MF plus aligned STLs.

- Added photo-free Blank card, Business card, and Membership card starter templates.
- Added a guided Design studio with separate Text, Logo, and Photo panels, original line icons, live font preview, palette-color buttons, and a clearer card canvas.
- Added a safe portable save path for scratch designs and a close prompt for unsaved changes.
- Added exact sampled face previews, nearest palette mapping for text/background, and standard 3MF base-material colors.
- Logo exports now build from the same isolated logo geometry and are written to a fresh folder so stale files cannot be mistaken for a new result.
- Logo extrusion uses exact cap boundaries and removes only sub-pixel contact points before the matching background is cut, preventing common non-manifold counter failures.

- Text and logo become flush, named front-layer geometry parts.
- A continuous solid backing keeps the back flat; the outer face remains flat too.
- Face is mirrored automatically for artwork-side-down printing.
- Bambu Studio part metadata includes suggested filament slots.
- Logo scaling and plain-background removal remain available.
- Logo editor now shows a transparency preview, supports enable/opacity controls, and exports a standalone named `CardForge_Logo.3mf` plus aligned/logo-only STLs.
- Logo extrusion now repairs tiny raster slits and narrow counters with a bounded close/open and a filtered triangulation fallback, preventing common “closed solid” export failures.
- Controls use grouped sections, consistent action hierarchy, and compact text icons so the five-step workflow is easier to follow.
- Added 30 bundled OFL sample fonts with live text previews.
- Next / Back navigation, Undo / Redo, and responsive export remain available.
- Direct face export includes optional NFC base and a print guide.

Download CardForge4D-Windows.zip, Extract All, and run `CardForge4D/CardForge4D.exe`. Keep `_internal` beside it. Python is not required. The extracted-folder package avoids the self-extracting one-file pattern that triggered antivirus heuristics on the previous build.

The build runs source tests, GUI controls, direct face export, packaged self-test, and a Microsoft Defender scan where Defender is available. Physical Bambu A1 printing, fine-feature readability, and production NFC fit require a local test print.
