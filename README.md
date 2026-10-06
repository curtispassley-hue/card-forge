# CardForge 4D 0.9 Studio Preview

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
5. Choose four artwork filament colors below the canvas; **5 Background** is independent. Painted regions and text retain their slot assignments when colors change. **Grayscale** temporarily uses gray tones; the same button becomes **Restore color**, which restores your saved color palette. **Reset colors** restores the default artwork palette without changing the background. Toggle **Print colors** to see the thresholded print result. Match the slots to your actual filaments in Bambu Studio.
6. **Export card** creates the face 3MF, aligned STLs, NFC base, project, and print guide. **Face only** omits the base. Choose a package name and destination in the export dialog. **Card & NFC** opens dimension settings; **Print checks** opens the printability report.

### Paint individual image elements

Select an image layer, then choose **Paint & refine image** in its inspector. The workshop edits the unrotated source; card size, position, and rotation are retained when you apply it.

- **Wand:** click an image element. Connected region only keeps separate islands separate, even if they share a color. Turn it off to select all similar colors. Tolerance controls how close colors must be.
- Choose filament **1–4**, then **Fill selection**. Assignments survive palette changes and save/load. Whole-silhouette recoloring in the inspector overrides region paints until you select **Original** or apply workshop edits.
- **Paint / Erase / Restore:** drag a brush. Its size is in source-image pixels. A selection constrains the brush; **Clear selection** allows painting anywhere. Restore recovers original pixels and removes paint assignments in the brushed area.
- **Grow / Shrink / Smooth** refine a selection. Use **Invert**, then **Erase** to remove pixels outside a refined outline. Filling a selection preserves antialiased edges; painting into transparency adds geometry.
- **Print edge threshold** controls which partly transparent pixels become solid. Lower values retain more of a soft edge. **Show printable edge** previews that cutoff at source resolution; inspect **Print colors** on the card for final print sampling.
- Use the mouse wheel or + / − to zoom, middle-drag to pan, and Fit to reset the view. Local Undo / Redo restore workshop changes. **Apply to card** makes one undoable card edit; **Cancel** discards the workshop copy.

Large images use a working copy no larger than 1600 × 1600 pixels; the imported file is never overwritten. This limit is shown when resampling occurs. Edits, paint maps, and restore pixels travel inside portable projects. Grayscale never overwrites the original image or stored color palette. Palettes already overwritten by an older release cannot be reconstructed automatically; choose Reset colors or set your preferred colors again.

Background is a fifth **design** control, not a promise of a fifth physical spool. If it matches an artwork color, the 3MF reuses that filament. If five different colors are configured, Print checks flags the need to share/remap a color for a four-spool setup. The background and backing retain their exact selected color rather than silently becoming another artwork color.

**Photo tools** is optional. It opens perspective correction, offline OCR, and logo extraction for a reference card photo. The photo itself is a layout reference; added image layers and editable text become printable geometry. The main workspace remains available throughout.

Thirty bundled sample fonts are included under the SIL Open Font License, each with its license file. The Windows release downloads this pinned library during its build, and a source checkout can recreate it with `python scripts/fetch_fonts.py`. They are available from the text editor's font picker and do not need to be installed in Windows. A custom TTF/OTF can still be selected.

Offline OCR uses RapidOCR and ONNX Runtime. OCR and background removal are assistants and should be reviewed. Transparent and antialiased logo edges are thresholded into the selected four colors. Tiny raster slits and narrow counters are automatically cleaned during extrusion so common display logos form closed solids reliably.

The Windows package is an extracted-folder application rather than a self-extracting one-file executable because unsigned one-file PyInstaller bundles can trigger antivirus heuristics. The build runs Microsoft Defender on the extracted app and publishes `defender-scan.json`; protection is never disabled. The package is unsigned, so no antivirus result can be guaranteed for every computer. If Windows blocks it, leave protection enabled and submit the file to Microsoft: https://www.microsoft.com/en-us/wdsi/filesubmission

Each export is written to a new named folder inside your selected destination. For example, exporting `My Card` creates `My_Card/My_Card_Face.3mf`, matching project/instruction files, and an `Aligned_STLs` folder. A second export creates `My_Card_2` so the earlier files remain intact. Unsupported Windows filename characters are replaced with underscores. The completion message names the exact output folder. Individual base/blank STL exports use the normal Save As dialog.

Automated tests cover direct face geometry, watertight overlapping image parts, flat exterior faces, named multipart 3MF output, stable filament assignments, independent background, reversible grayscale, connected selections, edge editing, paint restoration, 30 bundled fonts, OCR, portable multiple-image projects, logo tools, undo/redo, the naming/destination dialog, GUI startup, and responsive export. Physical A1 printing and production NFC fit still require a test print.

This preview adds original Windows application branding, executable version details, and an installed-dependency inventory with available license/notice files under `_internal/notices`. Font licenses remain bundled with the fonts. The program does not need Java. It is still an unsigned preview; paid activation and billing are not implemented. Source and third-party licenses are retained for distribution review.

The original HueForge import helpers remain only for opening older 0.4 projects; they are not part of the new face export workflow.
