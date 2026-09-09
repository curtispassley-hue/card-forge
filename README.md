# CardForge 4D 0.6 Alpha

CardForge turns a photographed business card into a two-piece, NFC-enabled card for the Bambu Lab A1. It now generates the face directly; HueForge is not required.

Download **CardForge4D-Windows.zip** from [Releases](https://github.com/curtispassley-hue/card-forge/releases). Choose **Extract All**, then launch `CardForge4D/CardForge4D.exe`. Keep the `_internal` folder beside the EXE. Python is not required. Do not run the EXE from inside the ZIP or copy it out by itself.

The face is a named multipart 3MF and an aligned STL set for Bambu Studio. The background and solid backing are continuous, while editable text and the logo occupy only the front layers. All parts meet flush; both exterior faces are flat. Open `CardForge_Face.3mf` in Bambu Studio and assign filaments under Objects / Parts. If using STLs, load every file in `Aligned_STLs` together as one multipart object and do not auto-arrange them. The model is mirrored for artwork-side-down printing already.

The default face is 0.8 mm: 0.4 mm of front color inlays and 0.4 mm of solid backing. The face must fit the base recess. Print the NFC base separately, install the tag, test-fit the face, and glue only after checking the fit. Inspect small lettering in Bambu Studio before printing.

## Editing workflow

1. Load and perspective-correct the card photo. The photo is a layout reference.
2. Scan text offline or add/edit text manually. Text becomes its own geometry part.
3. Load or extract a logo, preview its transparency, scale/position it, remove its plain background, and choose the four palette colors. Logo color regions become their own geometry parts. Use **Create Logo STL…** when you want only the logo parts.
4. Use Next / Back to move through Photo, Edit, Face / Colors, NFC / Assembly, and Printability. Undo / Redo and Ctrl+Z / Ctrl+Y restore edits.
5. Export the face 3MF/STLs, a standalone logo STL package when needed, and the NFC base. No HueForge step is needed.

Thirty bundled sample fonts are included under the SIL Open Font License, each with its license file. The Windows release downloads this pinned library during its build, and a source checkout can recreate it with `python scripts/fetch_fonts.py`. They are available from the text editor's font picker and do not need to be installed in Windows. A custom TTF/OTF can still be selected.

Offline OCR uses RapidOCR and ONNX Runtime. OCR and background removal are assistants and should be reviewed. Transparent and antialiased logo edges are thresholded into the selected four colors.

The Windows package is an extracted-folder application rather than a self-extracting one-file executable because unsigned one-file PyInstaller bundles can trigger antivirus heuristics. The build runs Microsoft Defender on the extracted app and publishes `defender-scan.json`; protection is never disabled. The package is unsigned, so no antivirus result can be guaranteed for every computer. If Windows blocks it, leave protection enabled and submit the file to Microsoft: https://www.microsoft.com/en-us/wdsi/filesubmission

Automated tests cover direct face geometry, watertight parts, flat exterior faces, named multipart 3MF output, four-color mapping, 30 bundled fonts, OCR, project round-trips, logo tools, undo/redo, navigation, GUI startup, and responsive export. Physical A1 printing and production NFC fit still require a test print.

The original HueForge import helpers remain only for opening older 0.4 projects; they are not part of the new face export workflow.
