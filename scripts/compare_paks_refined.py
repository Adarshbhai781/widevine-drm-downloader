"""Refined comparison: handle the __1 deduplication suffix properly.

The modded pak contains duplicate entries (modder used null-byte suffixes that
got sanitized to __1). We need to classify each modded file as:
  - identical_to_original: matches original file (same path, same content)
  - modified: same path exists in original but content differs
  - duplicate_of_modified: __1 version that matches the modded same-name file
  - duplicate_of_original: __1 version that matches the original same-name file
  - truly_new: file has no equivalent in original
  - junk_trap: in junk folder or matches trap keyword
"""
import hashlib
import csv
import re
from pathlib import Path
from collections import Counter

ORIG_ROOT = Path("/home/z/my-project/pak_workspace/UNPACK_ORIG/game_patch_4.5.0.21370_ORIGINAL/ShadowTrackerExtra")
MOD_ROOT  = Path("/home/z/my-project/pak_workspace/UNPACK/game_patch_4.5.0.21370/ShadowTrackerExtra")
OUT_DIR   = Path("/home/z/my-project/download")


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(root: Path):
    result = {}
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

# Strip the __N suffix to find the "logical" path
DEDUP_RE = re.compile(r"__(\d+)(\.[^.]+)?$")

def logical_path(rel: str) -> str:
    """Strip __N suffix to find the original logical filename."""
    m = DEDUP_RE.search(rel)
    if m:
        # Remove the __N part, keep extension
        suffix = m.group(2) or ""
        return rel[:m.start()] + suffix
    return rel


# Junk/trap detection
trap_keywords = ["NADEEM896211", "DSxDEMON", "PROTECTED", "ENCRYPTED", "ENC_",
                 "protected_", "win_invalid", "enc_fake", "enc_dictionary",
                 "enc_shield", "ENC_driver", "INDEX_ENCRYPTED", "PATCHED.txt"]
junk_dirs = {"0x454E435F494E444558", "DSxDEMON", "ENC_ROOT_PROTECT_0x7F",
             "ENCRYPTED_VOLUMEShadow\\x00", "ZSTDDIC_ENCRYPTED_ROOT",
             "protected_null_dir_path", "protected_system32_drivers",
             "protected_win_dir_", "_up_", "ENC_VIRTUAL", "server"}

def is_junk(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    if top in junk_dirs:
        return True
    fname = rel.rsplit("/", 1)[-1]
    return any(kw in fname for kw in trap_keywords)


# Classify every modded file
records = []  # (mod_rel, category, logical_path, mod_size, mod_sha, orig_size_if_any, orig_sha_if_any)
for rel, (_, size, msha) in mod_files.items():
    if is_junk(rel):
        records.append((rel, "junk_trap", logical_path(rel), size, msha, "", ""))
        continue
    log = logical_path(rel)
    if log in orig_files:
        o_size, o_sha = orig_files[log][1], orig_files[log][2]
        if msha == o_sha:
            records.append((rel, "identical_to_original", log, size, msha, o_size, o_sha))
        else:
            records.append((rel, "modified_version", log, size, msha, o_size, o_sha))
    else:
        # Logical path doesn't exist in original - is the rel itself (with __1) in original?
        if rel in orig_files:
            o_size, o_sha = orig_files[rel][1], orig_files[rel][2]
            if msha == o_sha:
                records.append((rel, "identical_to_original", rel, size, msha, o_size, o_sha))
            else:
                records.append((rel, "modified_version", rel, size, msha, o_size, o_sha))
        else:
            # Truly new file
            records.append((rel, "truly_new", log, size, msha, "", ""))

# Now classify duplicates: __1 files that match either the original or the modded same-name file
# Build a lookup of modded same-name files
mod_by_logical = {}
for rel, (_, size, msha) in mod_files.items():
    if is_junk(rel):
        continue
    log = logical_path(rel)
    mod_by_logical.setdefault(log, []).append((rel, msha))

# For each truly_new file, check if its logical path exists in modded with same hash (duplicate)
final_records = []
for rec in records:
    mod_rel, cat, log, msize, msha, osize, osha = rec
    if cat == "truly_new" and DEDUP_RE.search(mod_rel):
        # Check if any sibling with same logical path has the same content
        siblings = mod_by_logical.get(log, [])
        same_content_siblings = [s for s, h in siblings if s != mod_rel and h == msha]
        if same_content_siblings:
            # It's a duplicate of another (non-__1) modded file
            final_records.append((mod_rel, "duplicate_of_sibling", log, msize, msha, osize, osha))
            continue
    final_records.append(rec)

# Summary
cats = Counter(r[1] for r in final_records)
print()
print("=== REFINED SUMMARY ===")
for cat, n in cats.most_common():
    print(f"  {cat:<30} {n}")
print(f"  TOTAL                          {len(final_records)}")

# How many UNIQUE logical paths exist in modded that are NOT in original?
modded_logical_paths = set()
for rel, (p, size, msha) in mod_files.items():
    if is_junk(rel):
        continue
    modded_logical_paths.add(logical_path(rel))
orig_logical_paths = set(orig_files.keys())
truly_new_logical = modded_logical_paths - orig_logical_paths
print()
print(f"Unique logical paths in modded (excluding junk): {len(modded_logical_paths)}")
print(f"Unique logical paths in original:                {len(orig_logical_paths)}")
print(f"Logical paths truly added by modder:             {len(truly_new_logical)}")
print(f"Logical paths only in original (deleted):        {len(orig_logical_paths - modded_logical_paths)}")

# Save refined CSV
csv_path = OUT_DIR / "4.5.0_comparison_refined.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["category", "mod_rel_path", "logical_path", "mod_size", "mod_sha1", "orig_size", "orig_sha1"])
    for rec in final_records:
        w.writerow(rec)
print(f"\nRefined CSV saved: {csv_path}")

# Save detailed text report
txt_path = OUT_DIR / "4.5.0_comparison_refined.txt"
with open(txt_path, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("REFINED PAK COMPARISON REPORT\n")
    f.write("ORIGINAL (4.5.0 (1).pak, 11 MB, 884 files)  vs  MODDED (4.5.0.pak, 16.9 MB, 1804 files)\n")
    f.write("=" * 80 + "\n\n")
    f.write("CATEGORY COUNTS\n")
    f.write("-" * 50 + "\n")
    for cat, n in cats.most_common():
        f.write(f"  {cat:<30} {n}\n")
    f.write(f"  {'TOTAL':<30} {len(final_records)}\n\n")
    f.write(f"Unique logical paths in modded (excl. junk): {len(modded_logical_paths)}\n")
    f.write(f"Unique logical paths in original:                {len(orig_logical_paths)}\n")
    f.write(f"Truly-new logical paths added by modder:        {len(truly_new_logical)}\n")
    f.write(f"Logical paths deleted from original:            {len(orig_logical_paths - modded_logical_paths)}\n\n")

    # Group truly_new by area
    f.write("=" * 80 + "\n")
    f.write("CATEGORY: truly_new (genuinely new files added by modder, not duplicates)\n")
    f.write("=" * 80 + "\n")
    new_by_area = Counter()
    new_examples = {}
    for rec in final_records:
        if rec[1] == "truly_new":
            parts = rec[2].split("/")
            area = parts[1] if len(parts) >= 3 and parts[0] == "Content" else parts[0]
            new_by_area[area] += 1
            new_examples.setdefault(area, []).append(rec)
    for area, n in new_by_area.most_common():
        f.write(f"\n  --- {area} ({n} files) ---\n")
        for rec in new_examples[area][:5]:
            f.write(f"    {rec[0]}  ({rec[3]} bytes)\n")

    f.write("\n" + "=" * 80 + "\n")
    f.write("CATEGORY: modified_version (files where modder changed content)\n")
    f.write("=" * 80 + "\n")
    mod_by_area = Counter()
    for rec in final_records:
        if rec[1] == "modified_version":
            parts = rec[2].split("/")
            area = parts[1] if len(parts) >= 3 and parts[0] == "Content" else parts[0]
            mod_by_area[area] += 1
    for area, n in mod_by_area.most_common():
        f.write(f"  {area:<35} {n} files\n")

    f.write("\n" + "=" * 80 + "\n")
    f.write("CATEGORY: junk_trap (modder's anti-unpacker traps)\n")
    f.write("=" * 80 + "\n")
    for rec in final_records:
        if rec[1] == "junk_trap":
            f.write(f"  {rec[0]}  ({rec[3]} bytes)\n")
print(f"Refined TXT saved: {txt_path}")
