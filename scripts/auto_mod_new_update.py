#!/usr/bin/env python3
"""
=================================================================
  AUTO MOD - New Game Update Tool
  By Z.ai Agent
  
  Jab bhi naya game update aaye, ye script MOD automatically 
  apply kar dega naye PAK file pe.
  
  Kya karta hai:
  1. Mod template files ko naye PAK mein inject karta hai
  2. Expiry date change karta hai (default: 2027-12-31)
  3. Naya modded PAK banakar RESULT folder mein save karta hai
  
  Use:
    python auto_mod_new_update.py <new_pak_file.pak> [expiry_year]
    
  Example:
    python auto_mod_new_update.py game_patch_4.6.0.22000.pak
    python auto_mod_new_update.py game_patch_4.6.0.22000.pak 2028
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

# Mod files to inject (relative to template dir)
MOD_FILES = [
    ("Content/Lua/GameLua/Mod/BRMod/Gameplay/Core/BRPlayerCharacterBase.lua", "lua"),
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
    print("  🔧 AUTO MOD - New Game Update Tool")
    print("  By Z.ai Agent")
    print("=" * 60)
    print()

def validate_template_files():
    """Check all mod template files exist."""
    print("[1/6] Checking mod template files...")
    missing = []
    for rel_path, ftype in MOD_FILES:
        full_path = TEMPLATE_DIR / rel_path
        if not full_path.exists():
            missing.append(rel_path)
    
    if missing:
        print(f"  ❌ MISSING template files:")
        for m in missing:
            print(f"     - {m}")
        print(f"\n  Run extract_mod_templates.py first!")
        sys.exit(1)
    
    print(f"  ✅ All {len(MOD_FILES)} mod template files found")
    for rel_path, ftype in MOD_FILES:
        size = (TEMPLATE_DIR / rel_path).stat().st_size
        print(f"     ✓ {rel_path} ({size:,} bytes)")
    return True

def prepare_edit_folder(pak_file_path):
    """Clean and create EDIT folder with mod files."""
    print(f"\n[2/6] Preparing EDIT folder...")
    
    # Clean old EDIT folder
    if EDIT_DIR.exists():
        shutil.rmtree(EDIT_DIR)
    EDIT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy mod template files to EDIT folder
    # The EDIT folder structure needs to match PAK internal structure
    # For Option 4 (force_add), we need flat files + target path
    # For Option 3 (existing files), we need matching structure
    
    for rel_path, ftype in MOD_FILES:
        src = TEMPLATE_DIR / rel_path
        dst = EDIT_DIR / src.name  # Flat in EDIT folder
        
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  ✓ Copied: {src.name}")
        else:
            print(f"  ❌ Missing: {rel_path}")
    
    print(f"  ✅ EDIT folder ready: {EDIT_DIR}")
    return True

def patch_expiry_date(expiry_year):
    """Patch expiry date in BRPlayerCharacterBase.lua inside EDIT folder."""
    print(f"\n[3/6] Patching expiry date in BRPlayerCharacterBase.lua...")
    
    lua_path = EDIT_DIR / "BRPlayerCharacterBase.lua"
    if not lua_path.exists():
        print(f"  ❌ BRPlayerCharacterBase.lua not found in EDIT folder!")
        return False
    
    with open(lua_path, 'rb') as f:
        content = f.read()
    
    # Decode as text
    text = content.decode('utf-8', errors='replace')
    
    # Find and replace the expiry timestamp line
    # Pattern: year = YYYY, month = MM, day = DD
    old_pattern = r'year\s*=\s*\d{4},\s*month\s*=\s*\d{1,2},\s*day\s*=\s*\d{1,2},\s*hour\s*=\s*\d{1,2},\s*min\s*=\s*\d{1,2},\s*sec\s*=\s*\d{1,2}'
    new_date = f"year = {expiry_year}, month = {DEFAULT_EXPIRY_MONTH}, day = {DEFAULT_EXPIRY_DAY}, hour = {DEFAULT_EXPIRY_HOUR}, min = {DEFAULT_EXPIRY_MIN}, sec = {DEFAULT_EXPIRY_SEC}"
    
    new_text = re.sub(old_pattern, new_date, text)
    
    if new_text == text:
        print(f"  ⚠ Could not find expiry date pattern, trying alternative...")
        # Alternative: just replace the year
        new_text = re.sub(r'year\s*=\s*\d{4}', f'year = {expiry_year}', text)
    
    with open(lua_path, 'wb') as f:
        f.write(new_text.encode('utf-8'))
    
    print(f"  ✅ Expiry date changed to: {expiry_year}-{DEFAULT_EXPIRY_MONTH:02d}-{DEFAULT_EXPIRY_DAY:02d} {DEFAULT_EXPIRY_HOUR:02d}:{DEFAULT_EXPIRY_MIN:02d}:{DEFAULT_EXPIRY_SEC:02d}")
    
    # Verify
    with open(lua_path, 'r') as f:
        verify = f.read()
    match = re.search(r'year\s*=\s*(\d{4}),\s*month\s*=\s*(\d+),\s*day\s*=\s*(\d+)', verify)
    if match:
        print(f"  ✅ Verified: year={match.group(1)}, month={match.group(2)}, day={match.group(3)}")
    
    return True

def inject_mods_into_pak(pak_file_path, expiry_year):
    """Main function: Load PAK, inject mods, change expiry, repack."""
    pak_path = Path(pak_file_path).resolve()
    
    if not pak_path.exists():
        print(f"  ❌ PAK file not found: {pak_path}")
        return False
    
    print(f"\n[4/6] Loading PAK file: {pak_path.name}...")
    pak = TencentPakFile(pak_path)
    
    # Count files in PAK
    total_files = sum(len(d) for d in pak._index.values())
    print(f"  📦 PAK loaded: {total_files} files, version {pak._pak_info.version}")
    
    # Prepare result directory
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output_pak = RESULT_DIR / f"{pak_path.stem}_MODDED_{expiry_year}.pak"
    
    print(f"\n[5/6] Repacking with mod files...")
    print(f"  📁 EDIT dir: {EDIT_DIR}")
    print(f"  📦 Output: {output_pak.name}")
    
    # Try Option 4 first (force_add with target path for Lua)
    # The Lua file goes to: Content/Lua/GameLua/Mod/BRMod/Gameplay/Core/
    lua_target = "Content/Lua/GameLua/Mod/BRMod/Gameplay/Core"
    
    try:
        # First repack: Add all files to the Lua target path (Option 4 logic)
        count = repack_pak_file_full(pak, EDIT_DIR, output_pak, lua_target, force_add=True)
        
        if count > 0:
            print(f"\n  ✅ Successfully injected {count} mod files!")
        else:
            print(f"  ⚠ No files were injected. Trying without target path...")
            output_pak2 = RESULT_DIR / f"{pak_path.stem}_MODDED_{expiry_year}_v2.pak"
            count = repack_pak_file_full(pak, EDIT_DIR, output_pak2)
            if count > 0:
                output_pak = output_pak2
                print(f"\n  ✅ Successfully injected {count} mod files!")
            else:
                print(f"  ❌ Failed to inject files!")
                return False
        
    except Exception as e:
        print(f"  ❌ Repack failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return output_pak

def verify_repacked_pak(output_pak_path):
    """Verify the repacked PAK can be loaded."""
    print(f"\n[6/6] Verifying repacked PAK...")
    
    try:
        pak = TencentPakFile(output_pak_path)
        total_files = sum(len(d) for d in pak._index.values())
        
        # Check for mod files
        mod_found = 0
        for dir_path, files in pak._index.items():
            for name in files:
                if name in ["BRPlayerCharacterBase.lua", "BP_BattleRoyaleHUD.uasset", 
                            "BP_BattleRoyaleHUD.uexp", "PATCHED.txt"]:
                    mod_found += 1
                    print(f"  ✓ Found: {dir_path}{name}")
        
        print(f"\n  ✅ Repacked PAK verified!")
        print(f"  📦 Total files: {total_files}")
        print(f"  🔧 Mod files found: {mod_found}/4")
        print(f"  📁 Size: {output_pak_path.stat().st_size:,} bytes")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Verification failed: {e}")
        return False

def main():
    print_banner()
    
    # Parse arguments
    if len(sys.argv) < 2:
        print("USAGE:")
        print(f"  python {sys.argv[0]} <new_pak_file.pak> [expiry_year]")
        print()
        print("EXAMPLES:")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak")
        print(f"  python {sys.argv[0]} game_patch_4.6.0.22000.pak 2028")
        print()
        print("DEFAULT EXPIRY: 2027-12-31 23:59:59")
        print()
        
        # List available PAK files
        upload_dir = SCRIPTS_DIR.parent / "upload"
        if upload_dir.exists():
            pak_files = list(upload_dir.glob("*.pak"))
            if pak_files:
                print("Available PAK files in upload folder:")
                for p in sorted(pak_files):
                    size = p.stat().st_size
                    print(f"  📦 {p.name} ({size:,} bytes)")
        
        sys.exit(0)
    
    pak_file = sys.argv[1]
    expiry_year = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EXPIRY_YEAR
    
    print(f"🎯 Target PAK: {pak_file}")
    print(f"📅 Expiry Year: {expiry_year}")
    print(f"📖 Expiry Date: {expiry_year}-{DEFAULT_EXPIRY_MONTH:02d}-{DEFAULT_EXPIRY_DAY:02d} {DEFAULT_EXPIRY_HOUR:02d}:{DEFAULT_EXPIRY_MIN:02d}:{DEFAULT_EXPIRY_SEC:02d}")
    
    # Step 1: Validate templates
    validate_template_files()
    
    # Step 2: Prepare EDIT folder
    prepare_edit_folder(pak_file)
    
    # Step 3: Patch expiry date
    patch_expiry_date(expiry_year)
    
    # Step 4-5: Inject mods and repack
    result = inject_mods_into_pak(pak_file, expiry_year)
    
    if result and result is not True:
        # Step 6: Verify
        verify_repacked_pak(result)
        
        print()
        print("=" * 60)
        print(f"  ✅ MOD APPLY COMPLETE!")
        print(f"  📦 Output: {result}")
        print(f"  📁 Size: {result.stat().st_size:,} bytes")
        print(f"  📅 Expiry: {expiry_year}-12-31 23:59:59")
        print("=" * 60)
        print()
        print("  ⚡ Copy this PAK to your game folder and enjoy!")
        print()
    elif result is True:
        print("  ⚠ Repack returned True but no output path")
    else:
        print()
        print("=" * 60)
        print("  ❌ MOD FAILED - Check errors above")
        print("=" * 60)
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
