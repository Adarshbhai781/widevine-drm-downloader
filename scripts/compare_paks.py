"""Compare ORIGINAL vs MODDED 4.5.0 unpacked paks.

For each file (by relative path under ShadowTrackerExtra/), classify it as:
- common: same path exists in both
- only_in_original: file is in original but not modded
- only_in_modded: file is in modded but not original

For common files, compare SHA1 hash to detect modified files.

Output:
- Detailed CSV report
- Console summary
- Markdown summary
"""
import hashlib
import csv
import os
from pathlib import Path

ORIG_ROOT = Path("/home/z/my-project/pak_workspace/UNPACK_ORIG/game_patch_4.5.0.21370_ORIGINAL/ShadowTrackerExtra")
MOD_ROOT  = Path("/home/z/my-project/pak_workspace/UNPACK/game_patch_4.5.0.21370/ShadowTrackerExtra")
OUT_DIR   = Path("/home/z/my-project/download")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path):
    result = {}  # rel_path_str -> (abs_path, size, sha1)
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            result[rel] = (p, p.stat().st_size, sha1(p))
    return result


print("Scanning ORIGINAL...")
orig_files = walk(ORIG_ROOT)
print(f"  {len(orig_files)} files")

print("Scanning MODDED...")
mod_files = walk(MOD_ROOT)
print(f"  {len(mod_files)} files")

orig_set = set(orig_files.keys())
mod_set  = set(mod_files.keys())

common          = sorted(orig_set & mod_set)
only_in_orig    = sorted(orig_set - mod_set)
only_in_mod     = sorted(mod_set - orig_set)

modified = []
unchanged = []
for rel in common:
    o_size, o_sha = orig_files[rel][1], orig_files[rel][2]
    m_size, m_sha = mod_files[rel][1],  mod_files[rel][2]
    if o_sha != m_sha:
        modified.append((rel, o_size, o_size, m_size, m_sha, o_sha))
    else:
        unchanged.append(rel)

print()
print("=== SUMMARY ===")
print(f"Original total files: {len(orig_set)}")
print(f"Modded   total files: {len(mod_set)}")
print(f"Common (same path):   {len(common)}")
print(f"  - Unchanged (identical content): {len(unchanged)}")
print(f"  - Modified (different content):  {len(modified)}")
print(f"Only in ORIGINAL:     {len(only_in_orig)}")
print(f"Only in MODDED:       {len(only_in_mod)}")

# Categorize "only in modded" files
trap_keywords = ["NADEEM896211", "DSxDEMON", "PROTECTED", "ENCRYPTED", "ENC_",
                 "protected_", "win_invalid", "enc_fake", "enc_dictionary",
                 "enc_shield", "ENC_driver", "INDEX_ENCRYPTED", "PATCHED.txt"]
junk_dirs = ["0x454E435F494E444558", "DSxDEMON", "ENC_ROOT_PROTECT_0x7F",
             "ENCRYPTED_VOLUMEShadow", "ZSTDDIC_ENCRYPTED_ROOT",
             "protected_null_dir_path", "protected_system32_drivers",
             "protected_win_dir_", "_up_"]

mod_only_junk = []
mod_only_real = []
for rel in only_in_mod:
    is_junk = False
    # Check if path starts with a junk folder
    top = rel.split("/", 1)[0]
    if top in junk_dirs:
        is_junk = True
    # Check filename for trap keywords
    fname = rel.rsplit("/", 1)[-1]
    for kw in trap_keywords:
        if kw in fname:
            is_junk = True
            break
    if is_junk:
        mod_only_junk.append(rel)
    else:
        mod_only_real.append(rel)

print()
print("=== 'ONLY IN MODDED' BREAKDOWN ===")
print(f"  Junk/trap files (modder signatures, 0-byte dummies, etc.): {len(mod_only_junk)}")
print(f"  Real new files added by modder: {len(mod_only_real)}")

# Save CSV report
csv_path = OUT_DIR / "4.5.0_comparison_report.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["category", "relative_path", "orig_size", "orig_sha1", "mod_size", "mod_sha1"])
    for rel in unchanged:
        o = orig_files[rel]; w.writerow(["unchanged", rel, o[1], o[2], o[1], o[2]])
    for rel, os_, os2, ms, msha, osha in modified:
        w.writerow(["modified", rel, os_, osha, ms, msha])
    for rel in only_in_orig:
        o = orig_files[rel]; w.writerow(["only_in_original", rel, o[1], o[2], "", ""])
    for rel in mod_only_junk:
        m = mod_files[rel]; w.writerow(["modded_only_junk", rel, "", "", m[1], m[2]])
    for rel in mod_only_real:
        m = mod_files[rel]; w.writerow(["modded_only_real", rel, "", "", m[1], m[2]])
print(f"\nCSV saved: {csv_path}")

# Save plain-text detailed report
txt_path = OUT_DIR / "4.5.0_comparison_report.txt"
with open(txt_path, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("PAK COMPARISON REPORT - game_patch_4.5.0.21370\n")
    f.write("ORIGINAL (4.5.0 (1).pak, 11 MB)  vs  MODDED (4.5.0.pak, 16.9 MB)\n")
    f.write("=" * 80 + "\n\n")
    f.write("SUMMARY\n")
    f.write("-------\n")
    f.write(f"Original total files: {len(orig_set)}\n")
    f.write(f"Modded   total files: {len(mod_set)}\n")
    f.write(f"Common (same path):   {len(common)}\n")
    f.write(f"  - Unchanged (identical content): {len(unchanged)}\n")
    f.write(f"  - Modified (different content):  {len(modified)}\n")
    f.write(f"Only in ORIGINAL (missing from modded): {len(only_in_orig)}\n")
    f.write(f"Only in MODDED: {len(only_in_mod)}\n")
    f.write(f"  - Junk/trap files (modder signature/dummy): {len(mod_only_junk)}\n")
    f.write(f"  - Real new files added by modder:           {len(mod_only_real)}\n\n")

    f.write("=" * 80 + "\n")
    f.write("MODIFIED FILES (same path, different content)\n")
    f.write("=" * 80 + "\n")
    f.write(f"{'relative_path':<70} {'orig_size':>10} {'mod_size':>10}\n")
    f.write("-" * 80 + "\n")
    for rel, os_, os2, ms, msha, osha in modified:
        f.write(f"{rel:<70} {os_:>10} {ms:>10}\n")

    f.write("\n" + "=" * 80 + "\n")
    f.write("FILES ONLY IN ORIGINAL (missing from modded)\n")
    f.write("=" * 80 + "\n")
    for rel in only_in_orig:
        f.write(f"{rel}\n")

    f.write("\n" + "=" * 80 + "\n")
    f.write("REAL NEW FILES ADDED BY MODDER (filtered)\n")
    f.write("=" * 80 + "\n")
    for rel in mod_only_real:
        m = mod_files[rel]
        f.write(f"{rel}  ({m[1]} bytes)\n")

    f.write("\n" + "=" * 80 + "\n")
    f.write("JUNK / TRAP FILES ADDED BY MODDER (filtered)\n")
    f.write("=" * 80 + "\n")
    for rel in mod_only_junk:
        m = mod_files[rel]
        f.write(f"{rel}  ({m[1]} bytes)\n")
print(f"TXT saved: {txt_path}")
