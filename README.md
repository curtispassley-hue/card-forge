# CardForge Studio 1.0 Release Candidate


This release candidate extends the shared image/text editor to NFC cards, wall art, editable lightboxes, and artwork panels attached to a selected flat STL surface. Use **Set up object** to choose a template and dimensions, **Design** to edit images/text, and **Export** to choose a package name and destination. **Artwork / 3D** switches the same preview to the actual solid assembly.

Windows downloads include the portable ZIP and **CardForgeStudio-Setup.exe**, a per-user installer with an optional desktop shortcut. The executable remains **CardForge4D.exe**. Portable users must extract the whole ZIP and keep `_internal` beside it. No Python or Java installation is required. Windows 10/11 on x64 is required.

### New object workflows

- **Wall art:** rectangle/rounded rectangle or ellipse, editable artwork thickness, separate backing, desktop cradle or wall hanging holes.
- **Lightbox:** editable width/height, body depth, walls, fit clearance, artwork/diffuser thickness, LED width/thickness/cut interval/setback, cable exit, and removable back. Save/load lighting profiles. Print the fit coupons first. Desktop and wall presets are provided. The artwork is a separate panel in front of the shell, secured after checking fit and light leaks. The shell prints lip-down; the back prints exterior-down. The rear clearance-fit tongue is not a guaranteed retention mechanism; securing the back may require tape/fasteners after a test fit.
- **Artwork on imported STL:** import one closed solid of at most 250,000 triangles, choose mm/cm/inch, rotate the preview, and select a connected flat surface. Layout rescales to its bounds; review text/logo placement. The original mesh keeps its coordinates. Artwork is a separate outward-facing panel with an editable attachment gap. Export preserves alignment for inspection and provides a separate face-down artwork print. It does not carve an inlay or wrap curved surfaces.

Exports contain an assembled 3MF, aligned assembly STLs, independent **Print_Parts**, a portable project, and an assembly guide. Use **Print_Parts** for slicing; do not print a complete assembled lightbox as one object. Keep artwork color parts together as one multipart object. Assign filaments in Bambu Studio. Body, diffuser, and background may add colors beyond four artwork slots; remap/share spools or print body parts separately for an A1 four-spool setup.

Object bounds must fit a 256 mm A1 plate. Tiling, SVG/custom image-derived outlines, automatic curved wrapping, and controller/electrical design are not included. Printability checks validate dimensions and closed solids, but cannot replace slicer inspection, a fit test, or lighting temperature/stability testing.

The starter lighting profile is editable and unverified. An 8 mm, 5 V USB COB strip is a candidate; actual thickness, marked cut spacing, connector size, brightness and thermal behavior must be measured. No lighting kit is included or certified. Use the low-voltage kit's own power and installation instructions.

Changed projects are recovery-saved about once a minute to `%LOCALAPPDATA%/CardForgeStudio/Recovery.cardforge` when the app is idle. A recovery prompt appears after an interrupted session. Save a recovered project to your chosen destination. Unsaved field text must be applied before it reaches the saved project. Explicit project saves remain the source of truth; recovery is best effort.

For paid distribution setup and its outstanding release gates, see [COMMERCIAL_SETUP.md](COMMERCIAL_SETUP.md). Support contact: **curtispasley@gmail.com**.

CardForge turns a photographed business card into a two-piece, NFC-enabled card for the Bambu Lab A1. It now generates the face directly; HueForge is not required.

Download **CardForge4D-Windows.zip** from [Releases](https://github.com/curtispassley-hue/card-forge/releases). Choose **Extract All**, then launch `CardForge4D/CardForge4D.exe`. Keep the `_internal` folder beside the EXE. Python is not required. Do not run the EXE from inside the ZIP or copy it out by itself.

The custom dark studio uses original contour lines, object illustrations, and warm amber controls. These decorative graphics are UI-only and never appear in print output. The editor uses one main workspace with Layers on the left, your card in the center, the selected-item inspector on the right, and filament colors below. Choose an object in **Set up object**, or use **More card templates** for business and membership layouts. Add images and text in **Design**. Thirty bundled fonts are available in the text editor. Save a portable `.cardforge` project to keep the design, every image, and selected fonts together.

The face is a named multipart 3MF and an aligned STL set for Bambu Studio. The background and solid backing are continuous, while editable text and the logo occupy only the front layers. All parts meet flush; both exterior faces are flat. Open `CardForge_Face.3mf` in Bambu Studio and assign filaments under Objects / Parts. If using STLs, load every file in `Aligned_STLs` together as one multipart object and do not auto-arrange them. The model is mirrored for artwork-side-down printing already.

The default face is 0.8 mm: 0.4 mm of front color inlays and 0.4 mm of solid backing. The face must fit the base recess. Print the NFC base separately, install the tag, test-fit the face, and glue only after checking the fit. Inspect small lettering in Bambu Studio before printing.

## Editing workflow

1. Choose an object in **Set up object** or open a saved project, then choose **Design**. Use **Add image** to load one or several PNGs, or **Add text** to create lettering.
2. Select an item on the canvas or in **Layers**. Its inspector shows size and position. Enter **Width** or **Height** in millimeters; **Lock proportions** keeps the aspect ratio. Press Enter or leave the field to apply. Use the 10% buttons for quick sizing, or drag a corner handle.
3. Rotate images by any angle, flip them, center them, duplicate them, and change their order with **Forward / Backward**. Top layers appear in front; images sit above text. Arrow keys nudge the selected canvas item; Shift+arrow moves farther. Delete acts on the canvas selection. Undo / Redo restore edits.
4. Use **Remove background**, **Trim transparent edges**, per-image grayscale, and silhouette recoloring in the inspector. Original files are preserved. Selecting text exposes wording, size, font and filament controls in the same inspector. Press Enter or leave a field to apply.
5. Choose four artwork filament colors below the canvas; **Background** is independent. Painted regions and text retain their slot assignments when colors change. **Grayscale** temporarily uses gray tones; the same button becomes **Restore color**, which restores your saved color palette. **Reset colors** restores the default artwork palette without changing the background. Toggle **Print colors** to see the thresholded print result. Match the slots to your actual filaments in Bambu Studio.
6. Choose **Export**, enter a package name, choose a destination folder, and select **Complete object**, **Artwork panel only**, or **Images only**. **Export files** builds the package while keeping the interface responsive. **Review checks** opens the report. Return to **Set up object** for dimensions; expand fit, NFC or lighting settings when needed.

### Paint individual image elements

Select an image layer, then choose **Paint & refine image** in its inspector. The workshop opens inside the same window and edits the unrotated source; card size, position, and rotation are retained when you apply it.

- **Wand:** click an image element. Connected region only keeps separate islands separate, even if they share a color. Turn it off to select all similar colors. Tolerance controls how close colors must be.
- Choose filament **1–4**, then **Fill selection**. Assignments survive palette changes and save/load. Whole-silhouette recoloring in the inspector overrides region paints until you select **Original** or apply workshop edits.
- **Paint / Erase / Restore:** drag a brush. Its size is in source-image pixels. A selection constrains the brush; **Clear selection** allows painting anywhere. Restore recovers original pixels and removes paint assignments in the brushed area.
- **Grow / Shrink / Smooth** refine a selection. Use **Invert**, then **Erase** to remove pixels outside a refined outline. Filling a selection preserves antialiased edges; painting into transparency adds geometry.
- **Print edge threshold** controls which partly transparent pixels become solid. Lower values retain more of a soft edge. **Show printable edge** previews that cutoff at source resolution; inspect **Print colors** on the card for final print sampling.
- Use the mouse wheel or + / − to zoom, middle-drag to pan, and Fit to reset the view. Local Undo / Redo restore workshop changes. **Done painting** makes one undoable project edit; **Cancel painting** discards the working copy. Finish or cancel painting before changing phases or saving the project.

Large images use a working copy no larger than 1600 × 1600 pixels; the imported file is never overwritten. This limit is shown when resampling occurs. Edits, paint maps, and restore pixels travel inside portable projects. Grayscale never overwrites the original image or stored color palette. Palettes already overwritten by an older release cannot be reconstructed automatically; choose Reset colors or set your preferred colors again.

Background is a fifth **design** control, not a promise of a fifth physical spool. If it matches an artwork color, the 3MF reuses that filament. If five different colors are configured, Print checks flags the need to share/remap a color for a four-spool setup. The background and backing retain their exact selected color rather than silently becoming another artwork color.

**Trace a photo / scan text** in Design is optional. It opens perspective correction, offline OCR, and logo extraction for a reference card photo. The photo itself is a layout reference; added image layers and editable text become printable geometry. The main workspace remains available throughout.

Thirty bundled sample fonts are included under the SIL Open Font License, each with its license file. The Windows release downloads this pinned library during its build, and a source checkout can recreate it with `python scripts/fetch_fonts.py`. They are available from the text editor's font picker and do not need to be installed in Windows. A custom TTF/OTF can still be selected.

Offline OCR uses RapidOCR and ONNX Runtime. OCR and background removal are assistants and should be reviewed. Transparent and antialiased logo edges are thresholded into the selected four colors. Tiny raster slits and narrow counters are automatically cleaned during extrusion so common display logos form closed solids reliably.

The Windows package is an extracted-folder application rather than a self-extracting one-file executable because unsigned one-file PyInstaller bundles can trigger antivirus heuristics. The build runs Microsoft Defender on the extracted app and publishes `defender-scan.json`; protection is never disabled. The package is unsigned, so no antivirus result can be guaranteed for every computer. If Windows blocks it, leave protection enabled and submit the file to Microsoft: https://www.microsoft.com/en-us/wdsi/filesubmission

Each export is written to a new named folder inside your selected destination. For example, exporting `My Card` creates `My_Card/My_Card_Face.3mf`, matching project/instruction files, and an `Aligned_STLs` folder. A second export creates `My_Card_2` so the earlier files remain intact. Unsupported Windows filename characters are replaced with underscores. The completion message names the exact output folder. Individual base/blank STL exports use the normal Save As dialog.

Automated tests cover direct face geometry, watertight overlapping image parts, flat exterior faces, named multipart 3MF output, stable filament assignments, independent background, reversible grayscale, connected selections, edge editing, paint restoration, 30 bundled fonts, OCR, portable multiple-image projects, logo tools, undo/redo, the inline naming/destination controls, GUI startup, and responsive export. Physical A1 printing and production NFC fit still require a test print.

This preview adds original Windows application branding, executable version details, and an installed-dependency inventory with available license/notice files under `_internal/notices`. Font licenses remain bundled with the fonts. The program does not need Java. It is still an unsigned preview; signed offline license validation and an owner-only license issuer are available for a publisher-configured commercial build. This public release candidate is unrestricted for testing; checkout, signing credentials, and commercial terms still require owner setup. Source and third-party licenses are retained for distribution review.

The original HueForge import helpers remain only for opening older 0.4 projects; they are not part of the new face export workflow.
