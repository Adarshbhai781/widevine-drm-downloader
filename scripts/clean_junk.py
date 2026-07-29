#!/usr/bin/env python3
"""
Remove the modder's junk/trap files from the unpacked modded folder.

These are 0-byte files (and the 0-byte duplicates) that the modder
(NADEEM896211 / DSxDEMON) added as anti-unpacker traps. They contain
no real game content - just signatures like "INDEX_ENCRYPTED_BY_NADEEM896211.dat",
path-traversal attempts, null-byte names, etc.

After cleanup, only the real game files (884 original + 6 truly-new + 72 modified)
remain in the unpacked folder.
"""
import os
import shutil
from pathlib import Path

UNPACKED = Path("/home/z/my-project/pak_workspace/UNPACK/game_patch_4.5.0.21370/ShadowTrackerExtra")

# Patterns that identify junk/trap files added by the modder
JUNK_KEYWORDS = [
    'NADEEM896211', 'DSxDEMON', 'ENC_PROTECTED', 'ENC_VIRTUAL',
    'ENC_INVALID_PATH', 'INDEX_ENCRYPTED', 'vshadow_copy_ENCRYPTED',
    'fake_mount_ENCRYPTED', 'enc_dictionary_protected',
    'enc_fake_index_data', 'ENC_driver_cache', 'ASSET_FINDER',
    'ENC_PROTECTED_FILE', 'win_invalid_ENCRYPTED',
    'ENCRYPTED_BY_OFFICIAL', 'PATCHED.txt',
]

# Junk directories created by the modder (path traversal / null-byte names)
JUNK_DIRS = [
    '0x454E435F494E444558',
    'DSxDEMON',
    'ENC_ROOT_PROTECT_0x7F',
    'ZSTDDIC_ENCRYPTED_ROOT',
    'protected_null_dir_path',
    'protected_system32_drivers',
    'protected_win_dir_',
    '_up_',
    '_root_',
]

def is_junk_file(path: Path) -> bool:
    name = path.name
    # 0-byte files are always junk (real game files are never 0 bytes)
    if path.is_file() and path.stat().st_size == 0:
        return True
    # Match by keyword
    for kw in JUNK_KEYWORDS:
        if kw in name:
            return True
    return False

def is_junk_dir(path: Path) -> bool:
    for kw in JUNK_DIRS:
        if path.name == kw or path.name.startswith(kw):
            return True
    # Path-traversal residue
    if path.name.startswith('_up_') or '_up_' in path.name:
        return True
    # Encoded hex names like 0x454E435F494E444558
    if path.name.startswith('0x') and len(path.name) > 8:
        return True
    # Null-byte residue (backslashes from sanitize)
    if '\\\\server' in str(path) or '\\server' in path.name:
        return True
    return False

def main():
    print("=" * 70)
    print("  Cleaning modder's junk/trap files from unpacked folder")
    print("=" * 70)
    print(f"  Target: {UNPACKED}")
    print()

    # First pass: delete junk files
    removed_files = 0
    for root, dirs, files in os.walk(UNPACKED):
        root_path = Path(root)
        for f in files:
            fp = root_path / f
            if is_junk_file(fp):
                print(f"  [DEL] {fp.relative_to(UNPACKED)}  ({fp.stat().st_size} B)")
                fp.unlink()
                removed_files += 1

    # Second pass: delete junk directories (now that their files are gone)
    removed_dirs = 0
    # Walk bottom-up so we can delete empty parents too
    for root, dirs, files in os.walk(UNPACKED, topdown=False):
        root_path = Path(root)
        if root_path == UNPACKED:
            continue
        if is_junk_dir(root_path):
            # Force-remove even if not empty (residual junk)
            try:
                shutil.rmtree(root_path)
                print(f"  [RMDIR] {root_path.relative_to(UNPACKED)}/")
                removed_dirs += 1
            except Exception as e:
                print(f"  [SKIP] {root_path}: {e}")

    # Third pass: remove __1 duplicate files (modder's null-byte suffix trick)
    removed_dups = 0
    for root, dirs, files in os.walk(UNPACKED):
        root_path = Path(root)
        for f in files:
            if '__1.' in f or f.endswith('__1'):
                fp = root_path / f
                # Only delete if the canonical (non-__1) sibling exists
                if '__1.' in f:
                    sibling_name = f.replace('__1.', '.')
                else:
                    sibling_name = f[:-3]
                sibling = root_path / sibling_name
                if sibling.exists():
                    print(f"  [DEL-DUP] {fp.relative_to(UNPACKED)}")
                    fp.unlink()
                    removed_dups += 1

    print()
    print("=" * 70)
    print(f"  Cleanup complete.")
    print(f"  Junk files removed : {removed_files}")
    print(f"  Junk dirs removed  : {removed_dirs}")
    print(f"  Duplicate files removed (__1 suffix): {removed_dups}")
    print("=" * 70)

    # Count remaining files
    remaining = sum(1 for _ in UNPACKED.rglob('*') if _.is_file())
    print(f"  Remaining files in unpacked folder: {remaining}")

if __name__ == '__main__':
    main()
