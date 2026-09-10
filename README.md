# CardForge 4D 0.7.1 Preview

CardForge turns a photographed business card into a two-piece, NFC-enabled card for the Bambu Lab A1. It now generates the face directly; HueForge is not required.

Download **CardForge4D-Windows.zip** from [Releases](https://github.com/curtispassley-hue/card-forge/releases). Choose **Extract All**, then launch `CardForge4D/CardForge4D.exe`. Keep the `_internal` folder beside the EXE. Python is not required. Do not run the EXE from inside the ZIP or copy it out by itself.

This preview also includes a photo-free workflow. Choose Blank card, Business card, or Membership card on the Start screen, then add logos, PNG icons/emblems and editable text. The text editor includes 30 bundled sample fonts, live previews, and four filament-color choices. Save a portable `.cardforge` project to keep the design, every image, and selected fonts together.

The face is a named multipart 3MF and an aligned STL set for Bambu Studio. The background and solid backing are continuous, while editable text and the logo occupy only the front layers. All parts meet flush; both exterior faces are flat. Open `CardForge_Face.3mf` in Bambu Studio and assign filaments under Objects / Parts. If using STLs, load every file in `Aligned_STLs` together as one multipart object and do not auto-arrange them. The model is mirrored for artwork-side-down printing already.

The default face is 0.8 mm: 0.4 mm of front color inlays and 0.4 mm of solid backing. The face must fit the base recess. Print the NFC base separately, install the tag, test-fit the face, and glue only after checking the fit. Inspect small lettering in Bambu Studio before printing.

## Editing workflow

1. Load and perspective-correct the card photo. The photo is a layout reference.
2. Scan text offline or add/edit text manually. Text becomes its own geometry part.
3. Use **Add images** to select multiple PNGs for logos, icons and emblems. The **Images** panel lets you name, hide, resize, center and remove the background of each image. Drag images on the card to position them. The last image in the list is on top. The **Logo** panel still supports extracting a logo from a reference photo and opening older single-logo projects.
4. Choose the numbered tabs to move through Start, Design, Colors & export, Base & NFC, and Printability. The duplicate Next / Back row has been removed. Undo / Redo and Ctrl+Z / Ctrl+Y restore edits, including image cleanup and grayscale changes.
5. In **Colors & export**, choose your four filament colors. **Grayscale source and image elements** converts image tones without changing the source files or transparency. **Use four grayscale filaments** selects black, dark gray, light gray and white; match these slots to actual filaments in Bambu Studio. Text and the face background keep their selected colors and map to the palette.
6. Export the face 3MF/STLs, all image geometry as a standalone STL/3MF package when needed, and the NFC base. The export dialog lets you enter a **package name** and choose a **destination folder**. No HueForge step is needed.

Thirty bundled sample fonts are included under the SIL Open Font License, each with its license file. The Windows release downloads this pinned library during its build, and a source checkout can recreate it with `python scripts/fetch_fonts.py`. They are available from the text editor's font picker and do not need to be installed in Windows. A custom TTF/OTF can still be selected.

Offline OCR uses RapidOCR and ONNX Runtime. OCR and background removal are assistants and should be reviewed. Transparent and antialiased logo edges are thresholded into the selected four colors. Tiny raster slits and narrow counters are automatically cleaned during extrusion so common display logos form closed solids reliably.

The Windows package is an extracted-folder application rather than a self-extracting one-file executable because unsigned one-file PyInstaller bundles can trigger antivirus heuristics. The build runs Microsoft Defender on the extracted app and publishes `defender-scan.json`; protection is never disabled. The package is unsigned, so no antivirus result can be guaranteed for every computer. If Windows blocks it, leave protection enabled and submit the file to Microsoft: https://www.microsoft.com/en-us/wdsi/filesubmission

Each export is written to a new named folder inside your selected destination. For example, exporting `My Card` creates `My_Card/My_Card_Face.3mf`, matching project/instruction files, and an `Aligned_STLs` folder. A second export creates `My_Card_2` so the earlier files remain intact. Unsupported Windows filename characters are replaced with underscores. The completion message names the exact output folder. Individual base/blank STL exports use the normal Save As dialog.

Automated tests cover direct face geometry, watertight overlapping image parts, flat exterior faces, named multipart 3MF output, four-color and grayscale mapping, 30 bundled fonts, OCR, portable multiple-image projects, logo tools, undo/redo, the naming/destination dialog, GUI startup, and responsive export. Physical A1 printing and production NFC fit still require a test print.

The original HueForge import helpers remain only for opening older 0.4 projects; they are not part of the new face export workflow.
