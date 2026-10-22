"""Direct unpack driver for DHVIP.py - bypasses interactive menu.

Reads DHVIP.py, then calls its TencentPakFile class to unpack the .pak
specified on the command line, into the UNPACK folder next to DHVIP.py.
"""
import sys
import os
import traceback
from pathlib import Path

# Make sure the DHVIP.py file is importable
WORKSPACE = Path('/home/z/my-project/pak_workspace')
sys.path.insert(0, str(WORKSPACE))

# Import the DHVIP module
import importlib.util
spec = importlib.util.spec_from_file_location("dhvip", WORKSPACE / "DHVIP.py")
dhvip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dhvip)

pak_file = WORKSPACE / "PAK" / "game_patch_4.5.0.21370.pak"
unpack_path = WORKSPACE / "UNPACK" / pak_file.stem
repack_path = WORKSPACE / "REPACK" / pak_file.stem

print(f"[DRIVER] Unpacking {pak_file}")
print(f"[DRIVER] Target: {unpack_path}")

try:
    pak = dhvip.TencentPakFile(pak_file)
    pak.dump(unpack_path)
    log_path = unpack_path / f'Debug_{pak_file.stem}.log'
    dhvip.dump_unpacking_log(pak, log_path)
    # Use sanitized mount point + dir paths for repack scaffolding
    safe_mount = pak._sanitize_path(pak._mount_point)
    for dir_path, _ in pak._index.items():
        current_repack_path = repack_path / safe_mount / pak._sanitize_path(dir_path)
        current_repack_path.mkdir(parents=True, exist_ok=True)
    print(f"[DRIVER] SUCCESS - extracted to {unpack_path}")
except Exception as e:
    print(f"[DRIVER] FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
