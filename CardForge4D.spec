# PyInstaller spec for a portable Windows one-file GUI executable.
# RapidOCR model files are collected into the EXE so OCR works offline on the
# receiving Windows PC; no Tesseract install or administrator rights required.
from PyInstaller.utils.hooks import collect_all

datas=[]; binaries=[]; hiddenimports=[]
for pkg in ("cv2", "PIL", "shapely", "trimesh", "lxml", "rapidocr", "onnxruntime"):
    d,b,h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += [
    "onnxruntime.capi._pybind_state",
    "onnxruntime.capi.onnxruntime_pybind11_state",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts,
    [],
    name="CardForge4D",
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    uac_uiaccess=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="CardForge4D")
