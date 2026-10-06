CardForge 4D 0.8 Studio Preview

The editor now uses one main workspace: a layer list, card canvas, selected-item inspector, and filament palette. Card/NFC settings, print checks, and optional photo tracing open in utility windows. The five-step tab interface is removed.

- Select any image on the canvas or in Layers to edit width and height in millimeters. Lock proportions, use the 10% sizing buttons, or drag a corner handle. Edits apply with Enter or when leaving a field.
- Rotate by any angle or 90-degree steps; flip horizontally or vertically. Duplicate, hide, delete, move forward/backward, center, or nudge layers with arrow keys. Shift+arrow uses a larger nudge.
- Remove plain backgrounds, trim transparent padding, convert individual images to grayscale, or recolor their silhouettes to a filament slot. Original files are preserved; Undo restores edits.
- The editor and STL/3MF generator share image transformation code. Transformed parts remain flush and occupy only the front color layers.
- Toggle Print colors on the same canvas. Zoom, Fit, middle-drag panning, NFC guides, text editing, 30 fonts, and the four-filament palette remain available.
- Added original Windows app branding, executable version information, and a dependency/license inventory under `_internal/notices`. Fonts retain their bundled OFL files.
- Naming and destination selection remain available for every export package. Previous projects continue to open, and new image transformations are saved in portable projects.

Download CardForge4D-Windows.zip, Extract All, and run CardForge4D/CardForge4D.exe. Keep the whole extracted folder together. No Python or Java installation is required.

Automated checks cover transformed watertight geometry, flat exterior faces, image controls, corner resizing, ordering, undo, portable projects, output dialogs, minimum-window button labels, OCR, and the packaged executable. The Windows build also records its Defender scan result.

This is a preview, not a validated commercial release. Physical A1 printing and NFC fit still need testing. The executable is unsigned. Source and third-party licenses remain in effect; paid activation, billing, and a new commercial license are not included in this update.
