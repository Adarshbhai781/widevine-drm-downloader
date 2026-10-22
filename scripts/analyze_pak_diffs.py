#!/usr/bin/env python3
"""Analyze the exact byte-level edits in BP_PlayerPawn.uasset"""
import struct

path_m = "/home/z/my-project/pak_workspace/UNPACK/game_patch_4.5.0.21370/ShadowTrackerExtra/Content/BluePrints/Core/BP_PlayerPawn.uasset"
path_o = "/home/z/my-project/pak_workspace/UNPACK_ORIG/game_patch_4.5.0.21370_ORIGINAL/ShadowTrackerExtra/Content/BluePrints/Core/BP_PlayerPawn.uasset"

with open(path_m, 'rb') as f: m = f.read()
with open(path_o, 'rb') as f: o = f.read()

print(f"Modded size: {len(m)}  Original size: {len(o)}  Same: {len(m)==len(o)}")
print()

# Find AntiCheatManager in both
print("=== AntiCheatManager name entry ===")
for label, data in [("ORIG", o), ("MOD ", m)]:
    idx = data.find(b'AntiCheatManager')
    while idx != -1:
        length, = struct.unpack_from('<I', data, idx - 4)
        raw = data[idx:idx+length]
        print(f"  {label}: offset=0x{idx:x}, length_prefix={length}, stored={raw!r}")
        idx = data.find(b'AntiCheatManager', idx + 1)
        if idx == -1: break

# Find bHiddenInGame in modded
print()
print("=== bHiddenInGame (modder added) ===")
idx = m.find(b'bHiddenInGame')
if idx != -1:
    length, = struct.unpack_from('<I', m, idx - 4)
    print(f"  MOD: offset=0x{idx:x}, length_prefix={length}, stored={m[idx:idx+length]!r}")
    # What's around it?
    print(f"  Context (32B before): {m[idx-32:idx].hex()}")
    print(f"  Context (16B after):  {m[idx+length:idx+length+16].hex()}")

# Find bOwnerNoSee in modded
print()
print("=== bOwnerNoSee (modder added) ===")
idx = m.find(b'bOwnerNoSee')
if idx != -1:
    length, = struct.unpack_from('<I', m, idx - 4)
    print(f"  MOD: offset=0x{idx:x}, length_prefix={length}, stored={m[idx:idx+length]!r}")
    print(f"  Context (32B before): {m[idx-32:idx].hex()}")

# Find bApplyImpulseOnDamage - should only be in original
print()
print("=== bApplyImpulseOnDamage (removed by modder) ===")
idx_o = o.find(b'bApplyImpulseOnDamage')
idx_m = m.find(b'bApplyImpulseOnDamage')
print(f"  ORIG: offset=0x{idx_o:x}" if idx_o != -1 else "  ORIG: NOT FOUND")
print(f"  MOD:  offset=0x{idx_m:x}" if idx_m != -1 else "  MOD:  NOT FOUND (confirmed removed)")

# Find bOpened_EnableInputMode8Dirs
print()
print("=== bOpened_EnableInputMode8Dirs (removed by modder) ===")
idx_o = o.find(b'bOpened_EnableInputMode8Dirs')
idx_m = m.find(b'bOpened_EnableInputMode8Dirs')
print(f"  ORIG: offset=0x{idx_o:x}" if idx_o != -1 else "  ORIG: NOT FOUND")
print(f"  MOD:  offset=0x{idx_m:x}" if idx_m != -1 else "  MOD:  NOT FOUND (confirmed removed)")

# Now look at all 96 diff regions to understand the pattern
print()
print("=== Analyzing diff pattern (first 5 regions) ===")
diffs = []
for i in range(min(len(m), len(o))):
    if m[i] != o[i]:
        diffs.append(i)

# Group into regions
regions = []
if diffs:
    start = diffs[0]; prev = diffs[0]
    for off in diffs[1:]:
        if off == prev + 1:
            prev = off
        else:
            regions.append((start, prev))
            start = off; prev = off
    regions.append((start, prev))

print(f"Total regions: {len(regions)}")
for i, (s, e) in enumerate(regions[:5]):
    print(f"\n  Region {i+1}: 0x{s:x} - 0x{e:x} ({e-s+1} bytes)")
    print(f"    ORIG: {o[s-8:e+8].hex()}")
    print(f"    MOD:  {m[s-8:e+8].hex()}")
    o_ascii = ''.join(chr(b) if 32 <= b < 127 else '.' for b in o[s-8:e+8])
    m_ascii = ''.join(chr(b) if 32 <= b < 127 else '.' for b in m[s-8:e+8])
    print(f"    ORIG ASCII: {o_ascii}")
    print(f"    MOD  ASCII: {m_ascii}")

# Identify what each diff region is in
print()
print("=== Summary of changes ===")
print(f"  Total bytes changed: {len(diffs)}")
print(f"  Total diff regions: {len(regions)}")
print(f"  First region: 0x{regions[0][0]:x}")
print(f"  Last region:  0x{regions[-1][0]:x}")
print(f"  Span: 0x{regions[0][0]:x} - 0x{regions[-1][1]:x} ({regions[-1][1] - regions[0][0]} bytes)")
