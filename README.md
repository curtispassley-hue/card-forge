# CardForge 4D 0.4 Alpha

CardForge 4D converts a photographed business card into a two-piece 3D-printable NFC card workflow designed around a Bambu Lab A1 / AMS Lite and HueForge / FlatForge.

The physical idea is intentionally simple:

1. **Face** – a very thin HueForge/FlatForge print, printed face-down against the build plate so optical filament blending can create a much wider apparent color range from four actual filaments.
2. **Base** – a structural business-card-sized part containing the circular NFC recess and a shallow inset for the face.

Default finished X/Y size is **88.9 × 50.8 mm**. Z thickness is intentionally much greater than a paper business card and is user-adjustable.

## 0.4 additions

### Offline OCR-assisted text editing

CardForge now has an offline OCR module built around **RapidOCR + ONNX Runtime**. The Windows build bundles the OCR models inside the application, so the receiving PC does not need Tesseract, an OCR server, or an administrator installation.

`Scan Text (Offline OCR)`:

- scans the corrected card image,
- turns recognized text lines into editable CardForge text layers,
- estimates line position, approximate point size, and ink color,
- records OCR confidence,
- removes the photographed text from the background with an inpainting clean-plate pass,
- flags lower-confidence OCR lines in the printability report.

OCR is an assistant, not a guarantee. Business cards with unusual fonts, foil, gradients, glare, tiny text, or curved lettering should still be reviewed manually before printing.

### Editable logo extraction

`Extract Logo From Card` lets you drag a rectangle around a logo on the preview. CardForge:

- crops the selected logo,
- estimates the local background and creates transparency,
- removes the photographed logo region from the background,
- places the extracted logo back as a movable/resizable editable layer.

For best quality, replace an extracted logo with the company's original transparent PNG when one is available.

### Portable project files

The new default project format is **`.cardforge`**. It is a ZIP-based project bundle containing the project JSON plus current source/corrected/cleaned image assets and extracted logo. This fixes the temporary-file problem in earlier alphas and makes projects much safer to reopen or share.

Legacy `.cardforge.json` / `.json` projects are still readable.

## Existing 0.3 features retained

- automatic business-card detection and perspective correction,
- manual four-corner perspective correction,
- centered business-card crop fallback,
- editable text wording/font/size/color/position,
- direct drag positioning of text and logo,
- configurable four physical filament colors and names,
- full-color HueForge handoff image,
- nearest-four-filament preview,
- HueForge/FlatForge STL-folder import,
- HueForge/FlatForge 3MF import,
- X/Y-only normalization of imported HueForge geometry,
- strict preservation of HueForge Z/layer heights,
- standard 88.9 × 50.8 mm card size with editable dimensions,
- circular NFC presets plus custom size/thickness/clearance/X/Y,
- separate watertight NFC base STL,
- thin face test-fit STL,
- rotatable assembly preview,
- assembly-folder export,
- printability checks,
- Windows PyInstaller build configuration,
- GitHub Actions Windows build workflow.

## Recommended workflow

1. Photograph or scan a business card.
2. Load it in CardForge and run automatic perspective correction.
3. If necessary, use manual four-corner correction.
4. Run Offline OCR and verify every recognized text line.
5. Change fonts, wording, sizes, positions, and colors as needed.
6. Extract or replace the logo.
7. Choose the four actual filaments installed on the A1 / AMS Lite.
8. Export the HueForge handoff folder.
9. Open `CardForge_HueForge_Source.png` in HueForge.
10. Configure those same four filaments and tune HueForge's optical blending / transmission settings.
11. Export a FlatForge face-down STL set or supported multi-volume 3MF.
12. Import that geometry back into CardForge.
13. Configure the NFC tag and base dimensions.
14. Run Printability Checks.
15. Export the complete assembly folder.
16. Print the HueForge face face-down and the NFC base separately.
17. Install/test the NFC tag and fit the thin face into the base.

## Why CardForge does not replace HueForge

CardForge handles the business-card-specific job: perspective, editable text/logo, physical dimensions, NFC base, assembly, printability, and exchange files. HueForge remains the authoritative optical-blending and layer/color planning stage. CardForge deliberately preserves imported HueForge Z dimensions because changing layer heights can change the appearance of the blended image.

## Build the Windows executable

On a Windows 10/11 development PC:

1. Install 64-bit Python 3.12 for the current user. Administrator rights are not required.
2. Double-click `build_windows.bat`.
3. The script creates a local `.venv`, installs dependencies, runs the smoke tests, and builds:

`dist\CardForge4D.exe`

The finished EXE is configured **not** to request administrator privileges and includes the offline OCR runtime/models. It will be larger than the previous alpha because ONNX Runtime and OCR model files are bundled.

An unsigned executable distributed over the internet can still trigger Windows SmartScreen reputation warnings. That is separate from administrator privileges; a production release should eventually be code-signed.

## GitHub build

`.github/workflows/build-windows.yml` builds and uploads both:

- `CardForge4D.exe`
- `CardForge4D-Windows.zip`

This is the preferred reproducible Windows release route once the project is in a GitHub repository.

## Current alpha limitations

- OCR font-family identification is not automatic. OCR makes the wording editable, but the user selects the desired TTF/OTF font.
- Logo extraction is background-estimation based rather than full semantic AI segmentation.
- HueForge is still a handoff/import workflow; CardForge does not modify proprietary HueForge project internals.
- Interactive 3D preview is schematic rather than a full GPU mesh renderer.
- The application is not code-signed yet.

## Next target

The next development target is 0.5: OCR review/acceptance UI, font matching assistance, better logo/background segmentation, per-object hiding/locking, filament-library presets, and a Windows CI-produced executable for hands-on testing.
