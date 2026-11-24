"""Inspect official utility archives without running or installing third-party code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import datetime as dt

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAMES = ('kindle-usbnet-0.22.N-r19297.tar.xz', 'kual-mrinstaller-1.7.N-r19303.tar.xz')
USB_HASH = 'cf971557d42cc0a6d7699f1c743108c681fa41e3d67ee5802a91932d130d4032'

def safe_member(name: str) -> bool:
    value = PurePosixPath(name)
    return not value.is_absolute() and '..' not in value.parts and '\\' not in name and ':' not in name

def inspect_archive(path: Path, output: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name == PACKAGE_NAMES[0] and digest != USB_HASH:
        raise ValueError('USBNetwork digest differs from the same-firmware reference record. Stop and review; no device writes.')
    record = {'file': path.name, 'sha256': digest, 'bytes': path.stat().st_size,
              'hash_provenance': 'USB hash corroborated by paperwhite-weather fixed-commit device record; MRPI hash locally recorded, author listing has no digest',
              'members': [], 'review_text_files': []}
    with tarfile.open(path, 'r:xz') as archive:
        for member in archive.getmembers():
            if not safe_member(member.name):
                raise ValueError(f'Unsafe member path: {member.name}')
            record['members'].append({'name': member.name, 'bytes': member.size,
                                      'regular_file': member.isfile(), 'link': member.issym() or member.islnk()})
            # Copy only bounded text for human review, never executables, symlinks or .bin.
            name = PurePosixPath(member.name).name.lower()
            reviewable = (name.startswith(('readme', 'license', 'copying')) or name == 'mrinstaller.sh')
            if member.isfile() and 0 < member.size <= 512 * 1024 and reviewable:
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('Archive member could not be read')
                content = stream.read()
                if b'\x00' in content:
                    continue
                text = content.decode('utf-8', errors='replace')
                relative = PurePosixPath(member.name)
                target = output / path.name.replace('.tar.xz', '') / Path(*relative.parts)
                if not target.resolve().is_relative_to(output.resolve()):
                    raise ValueError('Review text escaped output directory')
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('x', encoding='utf-8') as handle:
                    handle.write(text)
                record['review_text_files'].append(str(target.relative_to(ROOT)))
    if not record['members']:
        raise ValueError('Archive is empty')
    return record

if __name__ == '__main__':
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output = ROOT / 'research' / ('usb-package-review-' + stamp)
    output.mkdir(parents=True, exist_ok=False)
    result = [inspect_archive(ROOT / 'packages' / name, output) for name in PACKAGE_NAMES]
    manifest = output / 'manifest.json'
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in result:
        print(f"{item['file']}\nSHA256: {item['sha256']}\nArchive entries: {len(item['members'])}")
    print('USB PACKAGES DOWNLOADED AND INSPECTED. NO KINDLE FILES MODIFIED.')
    print('Review manifest:', manifest)
    print('Installation is pending source review; do not copy or run the .bin files yet.')
