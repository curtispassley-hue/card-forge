CardForge 4D 0.6 Alpha

This release removes HueForge from the face production path. CardForge creates a direct Bambu Studio multipart 3MF plus aligned STLs.

- Text and logo become flush, named front-layer geometry parts.
- A continuous solid backing keeps the back flat; the outer face remains flat too.
- Face is mirrored automatically for artwork-side-down printing.
- Bambu Studio part metadata includes suggested filament slots.
- Logo scaling and plain-background removal remain available.
- Added 30 bundled OFL sample fonts with live text previews.
- Next / Back navigation, Undo / Redo, and responsive export remain available.
- Direct face export includes optional NFC base and a print guide.

Download CardForge4D-Windows.zip, Extract All, and run `CardForge4D/CardForge4D.exe`. Keep `_internal` beside it. Python is not required. The extracted-folder package avoids the self-extracting one-file pattern that triggered antivirus heuristics on the previous build.

The build runs source tests, GUI controls, direct face export, packaged self-test, and a Microsoft Defender scan where Defender is available. Physical Bambu A1 printing, fine-feature readability, and production NFC fit require a local test print.
