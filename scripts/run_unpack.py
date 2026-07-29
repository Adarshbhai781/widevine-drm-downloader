#!/usr/bin/env python3
# =============================================================================
# Unified PAK Unpacker  -  works for BOTH original AND modded (poisoned) paks
# -----------------------------------------------------------------------------
# This is a thin driver around DHVIP.py (the original tool by @MAMDANEILL /
# @DH_KING_of_WAR). It activates two safety patches that let the unpacker
# survive the anti-unpacker traps that modders (NADEEM896211 / DSxDEMON)
# inject into the pak's index:
#
#   1. RSA signature fallback   - if the publisher rotated RSA signing keys,
#      the RSA-based index hash assertion fails. We catch the AssertionError
#      and fall back to the SHA1 content hash (which is the real integrity
#      check and still passes).
#
#   2. Path sanitization        - modders embed null bytes (0x00), control
#      chars (0x7F DEL), Windows-invalid chars (? * < > | " :) and path
#      traversal sequences (../../etc) inside file/dir names. The sanitizers
#      `_sanitize_path_part` and `_sanitize_path` replace every forbidden
#      char with '_' so every entry can be safely extracted to disk.
#
# Usage:
#     python run_unpack.py <input.pak> <output_dir>
#
# Examples:
#     python run_unpack.py "game_patch_4.5.0.21370.pak"          ./OUT_MODDED
#     python run_unpack.py "game_patch_4.5.0.21370 (1).pak"      ./OUT_ORIGINAL
#     python run_unpack.py "game_patch_4.4.0.21156.pak"          ./OUT_440
# =============================================================================
import os
import sys
from pathlib import PurePath, Path

# Make sure DHVIP.py is importable
sys.path.insert(0, '/home/z/my-project/pak_workspace')
sys.path.insert(0, '/home/z/my-project/upload')

# Import the patched DHVIP module (it already contains the two safety patches)
from DHVIP import TencentPakFile


def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <input.pak> <output_dir>")
        print()
        print("Examples:")
        print('  python run_unpack.py "game_patch_4.5.0.21370.pak"      ./OUT_MODDED')
        print('  python run_unpack.py "game_patch_4.5.0.21370 (1).pak"  ./OUT_ORIGINAL')
        print('  python run_unpack.py "game_patch_4.4.0.21156.pak"      ./OUT_440')
        sys.exit(1)

    pak_path = PurePath(sys.argv[1])
    out_dir  = Path(sys.argv[2])

    if not os.path.exists(pak_path):
        print(f"ERROR: pak file not found: {pak_path}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"  Unpacking:  {pak_path.name}")
    print(f"  Output:     {out_dir}")
    print("=" * 70)

    pak = TencentPakFile(pak_path)
    print(f"  PAK version   : {pak._pak_info.version}")
    print(f"  Mount point   : {pak._mount_point}")
    print(f"  Index entries : {sum(len(d) for d in pak._index.values())}")
    print(f"  Directories   : {len(pak._index)}")
    print("-" * 70)
    pak.dump(out_dir)

    print()
    print("=" * 70)
    print(f"  DONE. Files extracted to: {out_dir}")
    print("=" * 70)


if __name__ == '__main__':
    main()
