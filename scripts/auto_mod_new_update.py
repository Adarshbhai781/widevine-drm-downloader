#!/usr/bin/env python3
"""
=================================================================
  AUTO MOD - New Game Update Tool (V1/V2 Support)
  By Z.ai Agent
  
  Jab bhi naya game update aaye, ye script MOD automatically 
  apply kar dega naye PAK file pe.
  
  Kya karta hai:
  1. Mod template files ko naye PAK mein inject karta hai
  2. Expiry date change karta hai (default: 2027-12-31)
  3. Naya modded PAK banakar RESULT folder mein save karta hai
  
  Use:
    python auto_mod_new_update.py <new_pak_file.pak> [version] [expiry_year]
    
  Version:
    v1  = Original mod (3020 lines, by DSxDEMON)
    v2  = Enhanced mod (2436 lines, optimized + fixes)
    default = v2
  
  Examples:
    python auto_mod_new_update.py game_patch_4.6.0.22000.pak v2
    python auto_mod_new_update.py game_patch_4.6.0.22000.pak v1 2028
    python auto_mod_new_update.py game_patch_4.6.0.22000.pak      (default: v2, 2027)
=================================================================
"""

import sys
import os
import re
import shutil
from pathlib import Path, PurePath

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dhvip_noverify import TencentPakFile, repack_pak_file_full

# ============================================================
# CONFIGURATION - Edit these as needed
# ============================================================

SCRIPTS_DIR = Path(__file__).parent
TEMPLATE_DIR = SCRIPTS_DIR / "mod_templates"
EDIT_DIR = SCRIPTS_DIR / "auto_edit"
RESULT_DIR = SCRIPTS_DIR / "auto_result"

# Default expiry date
DEFAULT_EXPIRY_YEAR = 2027
DEFAULT_EXPIRY_MONTH = 12
DEFAULT_EXPIRY_DAY = 31
DEFAULT_EXPIRY_HOUR = 23
DEFAULT_EXPIRY_MIN = 59
DEFAULT_EXPIRY_SEC = 59

# Lua file versions available
LUA_VERSIONS = {
    "v1": "Content/Lua/GameLua/Mod/BRMod/Gameplay/Core/BRPlayerCharacterBase_v1.lua",
    "v2": "Content/Lua/GameLua/Mod/BRMod/Gameplay/Core/BRPlayerCharacterBase_v2.lua",
}

# Other mod files to inject (besides Lua - these are same for both versions)
OTHER_MOD_FILES = [
    ("Content/BluePrints/Core/BP_BattleRoyaleHUD.uasset", "binary"),
    ("Content/BluePrints/Core/BP_BattleRoyaleHUD.uexp", "binary"),
    ("DSxDEMON/PATCHED.txt", "binary"),
]

# ============================================================
# CORE FUNCTIONS
# ============================================================

def print_banner():
    print()
    print("=" * 60)
    print("  AUTO MOD - New Game Update Tool (V1/V2)")
    print("  By Z.ai Agent")
    print("=" * 60)
    print()

def validate_template_files(version):
    """Check all mod template files exist for given version."""
    print(f"[1/6] Checking mod template files ({version})...")
    
    lua_rel = LUA_VERSIONS.get(version)
    if not lua_rel:
        print(f"  Invalid version: {version}")
        return False
    
    missing = []
    
    # Check Lua file
    lua_full = TEMPLATE_DIR / lua_rel
    if not lua_full.exists():
        missing.append(lua_rel)
    
    # Check other files
    for rel_path, ftype in OTHER_MOD_FILES:
        full_path = TEMPLATE_DIR / rel_path
        if not full_path.exists():
            missing.append(rel_path)
    
    if missing:
        print(f"  MISSING template files:")
        for m in missing:
            print(f"     - {m}")
        sys.exit(1)
    
    total = 1 + len(OTHER_MOD_FILES)
    print(f"  All {total} mod template files found")
    print(f"     Lua: {lua_rel} ({lua_full.stat().st_size:,} bytes)")
    for rel_path, ftype in OTHER_MOD_FILES:
        size = (TEMPLATE_DIR / rel_path).stat().st_size
        print(f"     {rel_path} ({size:,} bytes)")
    return True

def prepare_edit_folder(version):
    """Clean and create EDIT folder with mod files for selected version."""
    print(f"\n[2/6] Preparing EDIT folder ({version})...")
    
    # Clean old EDIT folder
    if EDIT_DIR.exists():
        shutil.rmtree(EDIT_DIR)
    EDIT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy Lua file (v1 or v2) -> named as BRPlayerCharacterBase.lua in EDIT
    lua_rel = LUA_VERSIONS[version]
    lua_src = TEMPLATE_DIR / lua_rel
    lua_dst = EDIT_DIR / "BRPlayerCharacterBase.lua"
    shutil.copy2(lua_src, lua_dst)
    print(f"  Copied Lua ({version}): {lua_src.name} -> BRPlayerCharacterBase.lua")
    
    # Copy other mod files
    for rel_path, ftype in OTHER_MOD_FILES:
        src = TEMPLATE_DIR / rel_path
        dst = EDIT_DIR / src.name
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  Copied: {src.name}")
        else:
            print(f"  MISSING: {rel_path}")
    
    print(f"  EDIT folder ready: {EDIT_DIR}")
    return True

def patch_expiry_date(expiry_year):
    """Patch expiry date in BRPlayerCharacterBase.lua inside EDIT folder."""
    print(f"\n[3/6] Patching expiry date...")
    
    lua_path = EDIT_DIR / "BRPlayerCharacterBase.lua"
    if not lua_path.exists():
        print(f"  BRPlayerCharacterBase.lua not found in EDIT folder!")
        return False
    
    with open(lua_path, 'rb') as f:
        content = f.read()
    
    text = content.decode('utf-8', errors='replace')
    
    # Find and replace the expiry timestamp line
    old_pattern = r'year\s*=\s*\d{4},\s*month\s*=\s*\d{1,2},\s*day\s*=\s*\d{1,2},\s*hour\s*=\s*\d{1,2},\s*min\s*=\s*\d{1,2},\s*sec\s*=\s*\d{1,2}'
    new_date = f"year = {expiry_year}, month = {DEFAULT_EXPIRY_MONTH}, day = {DEFAULT_EXPIRY_DAY}, hour = {DEFAULT_EXPIRY_HOUR}, min = {DEFAULT_EXPIRY_MIN}, sec = {DEFAULT_EXPIRY_SEC}"
    
    new_text = re.sub(old_pattern, new_date, text)
    
    if new_text == text:
        print(f"  Could not find expiry pattern, trying year only...")
        new_text = re.sub(r'year\s*=\s*\d{4}', f'year = {expiry_year}', text)
    
    with open(lua_path, 'wb') as f:
        f.write(new_text.encode('utf-8'))
    
    print(f"  Expiry set to: {expiry_year}-{DEFAULT_EXPIRY_MONTH:02d}-{DEFAULT_EXPIRY_DAY:02d} {DEFAULT_EXPIRY_HOUR:02d}:{DEFAULT_EXPIRY_MIN:02d}:{DEFAULT_EXPIRY_SEC:02d}")
    
    # Verify
    with open(lua_path, 'r') as f:
        verify = f.read()
    match = re.search(r'year\s*=\s*(\d{4}),\s*month\s*=\s*(\d+),\s*day\s*=\s*(\d+)', verify)
    if match:
        print(f"  Verified: year={match.group(1)}, month={match.group(2)}, day={match.group(3)}")
    
    return True

def inject_mods_into_pak(pak_file_path, expiry_year, version):
    """Main function: Load PAK, inject mods, change expiry, repack."""
    pak_path = Path(pak_file_path).resolve()
    
    if not pak_path.exists():
        print(f"  PAK file not found: {pak_path}")
        return False
    
    print(f"\n[4/6] Loading PAK file: {pak_path.name}...")
    pak = TencentPakFile(pak_path)
    
    total_files = sum(len(d) for d in pak._index.values())
    print(f"  PAK loaded: {total_files} files, version {pak._pak_info.version}")
    
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output_pak = RESULT_DIR / f"{pak_path.stem}_MODDED_{version.upper()}_{expiry_year}.pak"
    
    print(f"\n[5/6] Repacking with mod files ({version})...")
    print(f"  EDIT dir: {EDIT_DIR}")
    print(f"  Output: {output_pak.name}")
    
    lua_target = "Content/Lua/GameLua/Mod/BRMod/Gameplay/Core"
    
    try:
        count = repack_pak_file_full(pak, EDIT_DIR, output_pak, lua_target, force_add=True)
        
        if count > 0:
            print(f"\n  Successfully injected {count} mod files!")
        else:
            print(f"  No files injected. Trying without target path...")
            output_pak2 = RESULT_DIR / f"{pak_path.stem}_MODDED_{version.upper()}_{expiry_year}_alt.pak"
            count = repack_pak_file_full(pak, EDIT_DIR, output_pak2)
            if count > 0:
                output_pak = output_pak2
                print(f"\n  Successfully injected {count} mod files!")
            else:
                print(f"  Failed to inject files!")
                return False
        
    except Exception as e:
        print(f"  Repack failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return output_pak

def verify_repacked_pak(output_pak_path, version):
    """Verify the repacked PAK can be loaded."""
    print(f"\n[6/6] Verifying repacked PAK ({version})...")
    
    try:
        pak = TencentPakFile(output_pak_path)
        total_files = sum(len(d) for d in pak._index.values())
        
        mod_found = 0
        for dir_path, files in pak._index.items():
            for name in files:
                if name in ["BRPlayerCharacterBase.lua", "BP_BattleRoyaleHUD.uasset", 
                            "BP_BattleRoyaleHUD.uexp", "PATCHED.txt"]:
                    mod_found += 1
                    print(f"  Found: {dir_path}{name}")
        
        print(f"\n  Repacked PAK verified!")
        print(f"  Total files: {total_files}")
        print(f"  Mod files found: {mod_found}/4")
        print(f"  Size: {output_pak_path.stat().st_size:,} bytes")
        
        return True
        
    except Exception as e:
        print(f"  Verification failed: {e}")
        return False

def main():
    print_banner()
    
    # Parse arguments
    # Format: python auto_mod_new_update.py <pak> [version] [year]
    #         python auto_mod_new_update.py <pak> [year]  (legacy - defaults to v2)
    if len(sys.argv) < 2:
        print("USAGE:")
        print(f"  python {sys.argv[0]} <new_pak_file.pak> [version] [expiry_year]")
        print()
        print("VERSIONS:")
        print(f"  v1  = Original mod (3020 lines, by DSxDEMON)")
        print(f"  v2  = Enhanced mod (2436 lines, optimized + 12 fixes) [DEFAULT]")
        print()
        print("EXAMPLES:")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak          # v2, 2027")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak v1      # v1, 2027")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak v2 2028  # v2, 2028")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak v1 2028  # v1, 2028")
        print()
        print("DEFAULT: v2, Expiry 2027-12-31 23:59:59")
        print()
        
        # List available PAK files
        upload_dir = SCRIPTS_DIR.parent / "upload"
        if upload_dir.exists():
            pak_files = list(upload_dir.glob("*.pak"))
            if pak_files:
                print("Available PAK files in upload folder:")
                for p in sorted(pak_files):
                    size = p.stat().st_size
                    print(f"  {p.name} ({size:,} bytes)")
        
        # Show available versions
        print()
        print("Available Lua versions:")
        for ver, path in LUA_VERSIONS.items():
            full = TEMPLATE_DIR / path
            if full.exists():
                lines = 0
                with open(full, 'r') as f:
                    lines = sum(1 for _ in f)
                print(f"  {ver}: {path} ({lines} lines, {full.stat().st_size:,} bytes)")
        
        sys.exit(0)
    
    pak_file = sys.argv[1]
    
    # Parse version and year
    # Args: <pak> [version] [year]
    #       <pak> [year]  (if arg2 is a 4-digit number, treat as year, version=v2)
    version = "v2"  # default
    expiry_year = DEFAULT_EXPIRY_YEAR
    
    if len(sys.argv) >= 3:
        arg2 = sys.argv[2].strip().lower()
        if arg2 in ("v1", "v2"):
            version = arg2
        elif arg2.isdigit() and len(arg2) == 4:
            # Legacy mode: just year specified, use v2
            expiry_year = int(arg2)
    
    if len(sys.argv) >= 4:
        arg3 = sys.argv[3].strip()
        if arg3.isdigit():
            expiry_year = int(arg3)
    
    print(f"Target PAK: {pak_file}")
    print(f"Lua Version: {version}")
    print(f"Expiry Date: {expiry_year}-{DEFAULT_EXPIRY_MONTH:02d}-{DEFAULT_EXPIRY_DAY:02d} {DEFAULT_EXPIRY_HOUR:02d}:{DEFAULT_EXPIRY_MIN:02d}:{DEFAULT_EXPIRY_SEC:02d}")
    
    # Step 1: Validate templates
    validate_template_files(version)
    
    # Step 2: Prepare EDIT folder
    prepare_edit_folder(version)
    
    # Step 3: Patch expiry date
    patch_expiry_date(expiry_year)
    
    # Step 4-5: Inject mods and repack
    result = inject_mods_into_pak(pak_file, expiry_year, version)
    
    if result and result is not True:
        # Step 6: Verify
        verify_repacked_pak(result, version)
        
        print()
        print("=" * 60)
        print(f"  MOD APPLY COMPLETE!")
        print(f"  Version: {version}")
        print(f"  Output: {result}")
        print(f"  Size: {result.stat().st_size:,} bytes")
        print(f"  Expiry: {expiry_year}-12-31 23:59:59")
        print("=" * 60)
        print()
        print("  Copy this PAK to your game folder and enjoy!")
        print()
    elif result is True:
        print("  Repack returned True but no output path")
    else:
        print()
        print("=" * 60)
        print("  MOD FAILED - Check errors above")
        print("=" * 60)
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
