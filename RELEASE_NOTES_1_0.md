# CardForge Studio 1.0 Release Candidate

This revision fixes image painting and repeat exports, makes the 3D preview responsive, and adds body-only exports, illustrated assembly guides, and upgrade/uninstall support.

- Wand clicks replace the selection without a separate Clear action; Shift adds and Alt subtracts. A black/white boundary replaces the blue tint. Original image regions stay independently selectable after painting them the same filament.
- 3D rendering runs in a background worker, uses a lighter render while rotating, and reuses unchanged geometry. Export mesh detail is unchanged.
- Export **Complete object**, **Artwork panel only**, **Body / base parts only**, or images. Finish status stays inline with buttons to open the package and offline illustrated guide; continue editing and exporting in the same session.
- The installer updates the previous installed version and provides a Start Menu uninstall shortcut. **Menu → Updates / uninstall** explains installed and portable copies. Automated upgrade/removal tests preserve a user project.
- Template-specific text and illustrated HTML guides show NFC, wall art, lightbox, and flat-STL assembly, current project dimensions and lighting settings, included files and Bambu Studio print handling. Partial exports clearly identify omitted artwork/body parts.

NFC cards, wall art, editable desktop/wall lightboxes, and image panels on flat STL surfaces now share the same image/text workspace. Preserve your existing project files and test copies in this release.

New interface: a custom charcoal studio with warm amber accents, original object illustrations, subtle contour graphics, and a faint brand mark behind the preview. One canvas stays with you through **Set up object → Design → Export**. Text edits and image painting now stay in the main workspace, advanced fit/NFC/lighting settings collapse, and exports have persistent name/destination/package controls. Background graphics never enter artwork or print files.

Also includes: actual solid assembly preview; rectangle/ellipse outlines; body, diffuser, fit, mounting and LED dimension controls; saved lighting profiles; removable back, cable notch, fit coupons and desktop cradle; unit-aware flat surface selection and aligned imported-model export; idle recovery bundles; license/support panel and signed offline entitlements for configured commercial builds; Windows installer.

Includes the existing 30 sample fonts, multiple PNG layers, resize/rotate/flip controls, paint and edge workshop, stable filament assignments, independent background, reversible grayscale, undo/redo, offline OCR, and named destination exports. Artwork remains flush within the thin front layers. HueForge is not required.

Download **CardForgeStudio-Setup.exe** to install, or extract the complete **CardForge4D-Windows.zip** and run **CardForge4D/CardForge4D.exe**. Keep all accompanying files. The source ZIP and test reports are available alongside them.

Use **Set up object** to select an object and dimensions, **Design** to add and edit images/text, and **Export** to choose name, destination and package. Choose **Artwork / 3D** for the assembly preview. Finish image edits with **Done painting** or **Cancel painting**. Slice the independent Print_Parts, and read the assembly guide. The STL workflow attaches a separate panel to a selected flat surface; curved wrapping and carved inlays are not supported.

This is an unsigned release candidate with unrestricted testing exports. Commercial checkout, issuer configuration, publisher legal terms, code signing and physical A1/lightbox validation are still required before advertising a completed paid product. Source and third-party licenses remain in force. Antivirus results apply to the tested build and do not guarantee every computer's detection result. Leave protection enabled.
