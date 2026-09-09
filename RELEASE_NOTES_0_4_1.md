CardForge 4D 0.4.1 Alpha, built from the supplied CardForge4D_v0_4_alpha.zip.

- Correct NFC cavity depth below the face recess; default base is now 2.6 mm, leaving a 0.7 mm floor.
- Reject invalid or intersecting pocket dimensions instead of silently clipping the tag cavity.
- Correct STL face winding and preserve 3MF object transforms and instances.
- Render editable text at its selected physical point size.
- Carry imported face geometry and selected fonts inside portable projects.
- Refit imported geometry when dimensions change, preserving Z thickness.
- Pin build dependencies and include the missing geometry dependencies.
- Test the packaged EXE: GUI startup, watertight base, 3MF import, project round-trip and OCR with network connections disabled.

Download CardForge4D.exe and double-click it on 64-bit Windows. Python is not required.
First launch may take a few seconds while the portable application extracts its bundled runtime.

Workflow: load/correct a photo, edit text/logo, select four filaments, export the full-color HueForge handoff, import aligned FlatForge STL files or a compatible 3MF, run printability checks, and export the base and face. Print the thin face face-down and the NFC base separately. Preserve the HueForge layer/color plan and Z heights.

Alpha limits: the 3D view is a schematic assembly preview; logo extraction and OCR require review. The four-color preview does not simulate HueForge optical blending. Legacy JSON projects reference external assets. Physical Bambu A1 printing and production HueForge files have not been validated in this release. Measure your NFC tag and test-fit before gluing.
