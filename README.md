# CardForge 4D 0.8 Studio Preview

CardForge turns a photographed business card into a two-piece, NFC-enabled card for the Bambu Lab A1. It now generates the face directly; HueForge is not required.

Download **CardForge4D-Windows.zip** from [Releases](https://github.com/curtispassley-hue/card-forge/releases). Choose **Extract All**, then launch `CardForge4D/CardForge4D.exe`. Keep the `_internal` folder beside the EXE. Python is not required. Do not run the EXE from inside the ZIP or copy it out by itself.

The editor now uses one main workspace with Layers on the left, your card in the center, the selected-item inspector on the right, and filament colors below. Choose a Blank card, Business card, or Membership card from **New card**, then add images and text. Thirty bundled fonts are available in the text editor. Save a portable `.cardforge` project to keep the design, every image, and selected fonts together.

The face is a named multipart 3MF and an aligned STL set for Bambu Studio. The background and solid backing are continuous, while editable text and the logo occupy only the front layers. All parts meet flush; both exterior faces are flat. Open `CardForge_Face.3mf` in Bambu Studio and assign filaments under Objects / Parts. If using STLs, load every file in `Aligned_STLs` together as one multipart object and do not auto-arrange them. The model is mirrored for artwork-side-down printing already.

The default face is 0.8 mm: 0.4 mm of front color inlays and 0.4 mm of solid backing. The face must fit the base recess. Print the NFC base separately, install the tag, test-fit the face, and glue only after checking the fit. Inspect small lettering in Bambu Studio before printing.

## Editing workflow

1. Choose **New card** or open a saved project. Use **Add image** to load one or several PNGs, or **Add text** to create lettering.
2. Select an item on the canvas or in **Layers**. Its inspector shows size and position. Enter **Width** or **Height** in millimeters; **Lock proportions** keeps the aspect ratio. Press Enter or leave the field to apply. Use the 10% buttons for quick sizing, or drag a corner handle.
3. Rotate images by any angle, flip them, center them, duplicate them, and change their order with **Forward / Backward**. Top layers appear in front; images sit above text. Arrow keys nudge the selected canvas item; Shift+arrow moves farther. Delete acts on the canvas selection. Undo / Redo restore edits.
4. Use **Remove background**, **Trim transparent edges**, per-image grayscale, and silhouette recoloring in the inspector. Original files are preserved. Text size, wording, font, and filament color are available through **Edit text & font** or by double-clicking its layer.
5. Choose four filament colors below the canvas. **Grayscale** selects black, dark gray, light gray, and white and converts image tones. Toggle **Print colors** to see the printable palette on the same canvas. Match the slots to your actual filaments in Bambu Studio.
6. **Export card** creates the face 3MF, aligned STLs, NFC base, project, and print guide. **Face only** omits the base. Choose a package name and destination in the export dialog. **Card & NFC** opens dimension settings; **Print checks** opens the printability report.

**Photo tools** is optional. It opens perspective correction, offline OCR, and logo extraction for a reference card photo. The photo itself is a layout reference; added image layers and editable text become printable geometry. The main workspace remains available throughout.

Thirty bundled sample fonts are included under the SIL Open Font License, each with its license file. The Windows release downloads this pinned library during its build, and a source checkout can recreate it with `python scripts/fetch_fonts.py`. They are available from the text editor's font picker and do not need to be installed in Windows. A custom TTF/OTF can still be selected.

Offline OCR uses RapidOCR and ONNX Runtime. OCR and background removal are assistants and should be reviewed. Transparent and antialiased logo edges are thresholded into the selected four colors. Tiny raster slits and narrow counters are automatically cleaned during extrusion so common display logos form closed solids reliably.

The Windows package is an extracted-folder application rather than a self-extracting one-file executable because unsigned one-file PyInstaller bundles can trigger antivirus heuristics. The build runs Microsoft Defender on the extracted app and publishes `defender-scan.json`; protection is never disabled. The package is unsigned, so no antivirus result can be guaranteed for every computer. If Windows blocks it, leave protection enabled and submit the file to Microsoft: https://www.microsoft.com/en-us/wdsi/filesubmission

Each export is written to a new named folder inside your selected destination. For example, exporting `My Card` creates `My_Card/My_Card_Face.3mf`, matching project/instruction files, and an `Aligned_STLs` folder. A second export creates `My_Card_2` so the earlier files remain intact. Unsupported Windows filename characters are replaced with underscores. The completion message names the exact output folder. Individual base/blank STL exports use the normal Save As dialog.

Automated tests cover direct face geometry, watertight overlapping image parts, flat exterior faces, named multipart 3MF output, four-color and grayscale mapping, 30 bundled fonts, OCR, portable multiple-image projects, logo tools, undo/redo, the naming/destination dialog, GUI startup, and responsive export. Physical A1 printing and production NFC fit still require a test print.

This preview adds original Windows application branding, executable version details, and an installed-dependency inventory with available license/notice files under `_internal/notices`. Font licenses remain bundled with the fonts. The program does not need Java. It is still an unsigned preview; paid activation and billing are not implemented. Source and third-party licenses are retained for distribution review.

The original HueForge import helpers remain only for opening older 0.4 projects; they are not part of the new face export workflow.
