"""Build original Windows branding and collect installed dependency notices."""
from importlib import metadata
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cardforge.icons import icon_image


def main():
    assets = ROOT/'cardforge/assets'
    assets.mkdir(exist_ok=True)
    icon_image('app', size=256).save(assets/'CardForge.ico', sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)])
    (assets/'windows-version.txt').write_text('''VSVersionInfo(
  ffi=FixedFileInfo(filevers=(0,9,0,0), prodvers=(0,9,0,0), mask=0x3f, flags=2, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'CardForge 4D Studio'),
    StringStruct('FileVersion', '0.9.0 Preview'),
    StringStruct('InternalName', 'CardForge4D'),
    StringStruct('OriginalFilename', 'CardForge4D.exe'),
    StringStruct('ProductName', 'CardForge 4D'),
    StringStruct('ProductVersion', '0.9.0 Preview')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)''', encoding='utf-8')
    notices = assets/'notices'
    notices.mkdir(exist_ok=True)
    dependencies = []
    for line in (ROOT/'requirements.txt').read_text().splitlines():
        if '==' not in line: continue
        dist = metadata.distribution(line.split('==')[0])
        name = dist.metadata['Name']
        license_files = []
        for file in dist.files or []:
            p = Path(str(file))
            if '.dist-info' not in str(file) or not any(word in p.name.lower() for word in ('license', 'copying', 'notice')):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file(): continue
            metadata_index = next(i for i, part in enumerate(p.parts) if part.endswith('.dist-info'))
            destination = notices/name/Path(*p.parts[metadata_index+1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            license_files.append(str(destination.relative_to(notices)).replace('\\', '/'))
        dependencies.append({'name':name, 'version':dist.version,
            'license': dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See upstream project',
            'project_urls':dist.metadata.get_all('Project-URL') or [], 'notice_files':license_files})
    (notices/'dependencies.json').write_text(json.dumps(dependencies, indent=2), encoding='utf-8')
    (notices/'README.txt').write_text('Third-party packages retain their own licenses. This inventory describes the build environment, including build tools. Bundled fonts include their OFL files in assets/fonts. Review applicable licenses before commercial distribution. CardForge source license is in LICENSE.txt.\n', encoding='utf-8')
    print('Windows icon, version metadata and dependency notices prepared.')


if __name__ == '__main__': main()
