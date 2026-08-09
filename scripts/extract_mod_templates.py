#!/usr/bin/env python3
"""
Extract mod template files from the modded PAK (by @DSxDEMON)
These templates will be reused for future game updates.
"""

import sys
import os

# Add scripts dir to path so we can import dhvip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dhvip_noverify import TencentPakFile
from pathlib import Path

# Paths
MODDED_PAK = Path("/home/z/my-project/upload/game_patch_4.5.0.21370.pak")
TEMPLATE_DIR = Path("/home/z/my-project/scripts/mod_templates")

# Known mod files added by @DSxDEMON
MOD_FILE_PATTERNS = [
    "BRPlayerCharacterBase.lua",
    "BP_BattleRoyaleHUD.uasset",
    "BP_BattleRoyaleHUD.uexp",
    "PATCHED.txt",
]

def extract_mod_templates():
    """Extract the 4 mod files from the modded PAK and save as templates."""
    print(f"[1/3] Loading modded PAK: {MODDED_PAK.name}...")
    pak = TencentPakFile(MODDED_PAK)
    
    print(f"[2/3] Extracting mod files...")
    
    found_files = []
    
    # List all files to find our mod files
    for dir_path, files in pak._index.items():
        for name, entry in files.items():
            for pattern in MOD_FILE_PATTERNS:
                if name == pattern:
                    # Extract this file using _write_to_disk method
                    rel_path = str(dir_path).strip('/')
                    save_dir = TEMPLATE_DIR / rel_path
                    save_dir.mkdir(parents=True, exist_ok=True)
                    
                    save_path = save_dir / name
                    pak._write_to_disk(save_path, entry)
                    
                    size = save_path.stat().st_size
                    full_path = f"{dir_path}{name}"
                    found_files.append((full_path, str(save_path), size))
                    print(f"  ✓ Saved: {full_path} ({size} bytes)")
                    break
    
    print(f"\n[3/3] Summary:")
    print(f"  Total mod files extracted: {len(found_files)}")
    for fp, sp, sz in found_files:
        print(f"  - {fp} ({sz} bytes)")
    
    # Save metadata
    meta_path = TEMPLATE_DIR / "mod_info.txt"
    with open(meta_path, 'w') as f:
        f.write(f"Mod by: @DSxDEMON\n")
        f.write(f"Source PAK: {MODDED_PAK.name}\n")
        f.write(f"Files:\n")
        for fp, sp, sz in found_files:
            f.write(f"  {fp} -> {sp}\n")
        f.write(f"\nExpiry date in BRPlayerCharacterBase.lua: 2027-12-31 23:59:59\n")
    
    print(f"\n✅ Mod templates saved to: {TEMPLATE_DIR}")
    print(f"✅ Metadata saved to: {meta_path}")

if __name__ == '__main__':
    extract_mod_templates()
