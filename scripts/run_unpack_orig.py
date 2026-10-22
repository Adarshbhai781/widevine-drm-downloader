"""Unpack driver for game_patch_4.5.0.21370 (1).pak (the suspected original).

Uses the patched DHVIP module with sanitization bypass.
"""
import sys
import os
import traceback
from pathlib import Path

WORKSPACE = Path('/home/z/my-project/pak_workspace')
sys.path.insert(0, str(WORKSPACE))

import importlib.util
spec = importlib.util.spec_from_file_location("dhvip", WORKSPACE / "DHVIP.py")
dhvip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dhvip)

pak_file = WORKSPACE / "PAK_ORIG" / "game_patch_4.5.0.21370.pak"
unpack_path = WORKSPACE / "UNPACK_ORIG" / "game_patch_4.5.0.21370_ORIGINAL"
repack_path = WORKSPACE / "REPACK_ORIG" / "game_patch_4.5.0.21370_ORIGINAL"

print(f"[DRIVER] Unpacking {pak_file}")
print(f"[DRIVER] Target: {unpack_path}")
unpack_path.mkdir(parents=True, exist_ok=True)

try:
    pak = dhvip.TencentPakFile(pak_file)
    print(f"[DRIVER] version={pak._pak_info.version} files={len(pak._files)} dirs={len(pak._index)} mount={pak._mount_point}")
    pak.dump(unpack_path)
    log_path = unpack_path / f'Debug_{pak_file.stem}.log'
    dhvip.dump_unpacking_log(pak, log_path)
    safe_mount = pak._sanitize_path(pak._mount_point)
    for dir_path, _ in pak._index.items():
        current_repack_path = repack_path / safe_mount / pak._sanitize_path(dir_path)
        current_repack_path.mkdir(parents=True, exist_ok=True)
    print(f"[DRIVER] SUCCESS - extracted to {unpack_path}")
except Exception as e:
    print(f"[DRIVER] FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
