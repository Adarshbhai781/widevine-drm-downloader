#!/usr/bin/env python3
"""
Python mp4decrypt - CENC AES-CTR decryption for MP4/DASH segments
==================================================================
Properly parses moof/traf/senc boxes for per-sample IVs and subsamples,
matches KIDs from tenc boxes with provided keys, decrypts mdat using AES-CTR,
and removes encryption markers (senc, saiz, saio) from moof after decryption.

Usage:
    python3 mp4decrypt.py --key <kid1>:<key1> [--key <kid2>:<key2>] ... <input.mp4> <output.mp4>
"""

import sys
import os
import struct
import io
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# ─── AES-CTR ──────────────────────────────────────────────────────────────
def aes_ctr_decrypt(data, key_bytes, iv_8):
    """Decrypt with AES-CTR. IV is 8 bytes, extended to 16 with trailing zeros.
    
    Per ISO 23001-7 (CENC), the 8-byte IV is placed in the first 8 bytes
    of the 16-byte CTR IV, with the remaining 8 bytes set to zero.
    """
    iv_16 = iv_8 + b'\x00' * 8
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(iv_16))
    dec = cipher.decryptor()
    return dec.update(data) + dec.finalize()

# ─── MP4 Box Iterator ────────────────────────────────────────────────────
def iter_boxes(data, start=0, end=None):
    """Yield (box_type, box_offset, box_size, header_size) for boxes."""
    if end is None:
        end = len(data)
    offset = start
    while offset < end - 8:
        if offset + 8 > end:
            break
        size = struct.unpack('>I', data[offset:offset+4])[0]
        box_type = data[offset+4:offset+8]
        header_size = 8
        if size == 1:  # 64-bit extended size
            if offset + 16 > end:
                break
            size = struct.unpack('>Q', data[offset+8:offset+16])[0]
            header_size = 16
        elif size == 0:  # rest of file
            size = end - offset
        if size < 8 or offset + size > end:
            break
        yield box_type, offset, size, header_size
        offset += size

# ─── Parse tenc box ──────────────────────────────────────────────────────
def parse_tenc(data, offset, size):
    """Parse tenc (track encryption) box. Returns default_KID as hex string."""
    # tenc is a FullBox: 8 bytes header + 4 bytes (version+flags) 
    # version 0: 1 byte default_isProtected + 3 byte default_Per_Sample_IV_Size + 16 byte default_KID
    # version 1: same + 1 byte default_constantIVSize + default_constantIV
    header_size = 8
    if offset + header_size + 4 > offset + size:
        return None
    
    version = data[offset + header_size]
    # flags = bytes 9-11
    pos = offset + header_size + 4  # after version+flags
    
    if pos + 4 > offset + size:
        return None
    
    default_is_protected = data[pos]
    default_per_sample_iv_size = data[pos + 1]
    # 2 bytes reserved/algorithm_id (version 1 has different layout)
    pos += 4  # skip is_protected(1) + per_sample_iv_size(1) + reserved(2)
    
    if default_is_protected == 0:
        return None  # not encrypted
    
    # Read default_KID (16 bytes)
    if pos + 16 > offset + size:
        return None
    
    kid_bytes = data[pos:pos+16]
    return kid_bytes.hex()

# ─── Parse senc box ──────────────────────────────────────────────────────
def parse_senc(data, offset, size):
    """Parse a senc box. Returns list of (iv_8bytes, [(clear, encrypted), ...])."""
    header_size = 8
    if offset + header_size + 8 > offset + size:
        return []
    
    version = data[offset + header_size]
    flags = (data[offset+9] << 16) | (data[offset+10] << 8) | data[offset+11]
    has_subsamples = bool(flags & 0x02)  # flag bit 1 = subsample encryption
    
    sample_count = struct.unpack('>I', data[offset+12:offset+16])[0]
    iv_size = 8 if version == 0 else 16
    
    pos = offset + 16
    samples = []
    
    for i in range(sample_count):
        if pos + iv_size > offset + size:
            break
        iv = data[pos:pos+iv_size]
        pos += iv_size
        
        subsamples = []
        if has_subsamples:
            if pos + 2 > offset + size:
                break
            n_sub = struct.unpack('>H', data[pos:pos+2])[0]
            pos += 2
            for j in range(n_sub):
                if pos + 6 > offset + size:
                    break
                clear = struct.unpack('>H', data[pos:pos+2])[0]
                encrypted = struct.unpack('>I', data[pos+2:pos+6])[0]
                pos += 6
                subsamples.append((clear, encrypted))
        
        # Use only first 8 bytes of IV (CENC spec)
        iv_8 = iv[:8] if len(iv) >= 8 else iv + b'\x00' * (8 - len(iv))
        samples.append((iv_8, subsamples))
    
    return samples

# ─── Parse traf for encryption info ─────────────────────────────────────
def parse_traf_for_decrypt(data, traf_offset, traf_size):
    """Parse traf box to extract encryption info (senc) and KID (from tenc)."""
    traf_end = traf_offset + traf_size
    samples = None
    kid = None
    
    for box_type, box_offset, box_size, hdr_size in iter_boxes(data, traf_offset + 8, traf_end):
        if box_type == b'senc':
            samples = parse_senc(data, box_offset, box_size)
        elif box_type == b'tenc':
            kid = parse_tenc(data, box_offset, box_size)
    
    # If no tenc in traf, look inside saiz/saio referenced senc
    # (fallback - we'll use the KID from moov/tenc or try all keys)
    
    return samples, kid

# ─── Find KID from moov ─────────────────────────────────────────────────
def find_kid_from_moov(data):
    """Find default KID from moov/trak/mdia/minf/stbl/stsd/.../tenc or sinf/schm/tenc."""
    for box_type, box_offset, box_size, hdr_size in iter_boxes(data, 0, len(data)):
        if box_type == b'moov':
            moov_end = box_offset + box_size
            # Recursively search for tenc inside moov
            return _find_tenc_recursive(data, box_offset + 8, moov_end)
    return None

def _find_tenc_recursive(data, start, end):
    """Recursively search for tenc box."""
    for box_type, box_offset, box_size, hdr_size in iter_boxes(data, start, end):
        if box_type == b'tenc':
            kid = parse_tenc(data, box_offset, box_size)
            if kid:
                return kid
        # Recurse into container boxes
        container_types = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'stsd', 
                          b'sinf', b'schi', b'moof', b'traf', b'encv', b'enca'}
        if box_type in container_types:
            result = _find_tenc_recursive(data, box_offset + hdr_size, box_offset + box_size)
            if result:
                return result
    return None

# ─── Remove encryption boxes from moof ──────────────────────────────────
def strip_moof(data, moof_offset, moof_size):
    """Remove senc, saiz, saio boxes from moof and update sizes.
    Returns modified moof data."""
    moof_end = moof_offset + moof_size
    moof_data = bytearray(data[moof_offset:moof_end])
    
    # Collect boxes to remove (relative to moof start)
    boxes_to_remove = []
    _find_boxes_to_remove(moof_data, 0, len(moof_data), boxes_to_remove)
    
    if not boxes_to_remove:
        return bytes(moof_data)
    
    # Remove boxes (from end to start to preserve offsets)
    total_removed = 0
    for rel_offset, box_size in sorted(boxes_to_remove, reverse=True):
        del moof_data[rel_offset:rel_offset + box_size]
        total_removed += box_size
    
    # Update moof box size
    new_moof_size = len(moof_data)
    struct.pack_into('>I', moof_data, 0, new_moof_size)
    
    return bytes(moof_data)

def _find_boxes_to_remove(data, start, end, result):
    """Find senc, saiz, saio boxes recursively."""
    remove_types = {b'senc', b'saiz', b'saio'}
    container_types = {b'moof', b'traf'}
    
    for box_type, box_offset, box_size, hdr_size in iter_boxes(data, start, end):
        if box_type in remove_types:
            result.append((box_offset, box_size))
        elif box_type in container_types:
            _find_boxes_to_remove(data, box_offset + hdr_size, box_offset + box_size, result)
            # Update container box size after children are processed
            # (we'll rebuild from scratch below, so this is handled by strip_moof)

# ─── Decrypt mdat using sample info ──────────────────────────────────────
def decrypt_mdat(mdat_data, samples, key_bytes):
    """Decrypt mdat content using per-sample IVs and subsample patterns.
    
    In CENC AES-CTR, all encrypted portions within a single sample
    share the same CTR counter stream. So we concatenate all encrypted
    bytes for a sample, decrypt once, then split back into subsamples.
    """
    result = bytearray()
    data_offset = 0
    
    for iv_8, subsamples in samples:
        if not subsamples:
            # Full sample encryption
            sample_size = len(mdat_data) - data_offset
            enc_data = mdat_data[data_offset:data_offset + sample_size]
            dec_data = aes_ctr_decrypt(enc_data, key_bytes, iv_8)
            result.extend(dec_data)
            data_offset += sample_size
        else:
            # Subsample encryption - collect all encrypted parts, decrypt as one
            sample_offset = data_offset
            total_enc_size = 0
            enc_parts = []
            
            for clear_size, encrypted_size in subsamples:
                if clear_size > 0:
                    sample_offset += clear_size
                if encrypted_size > 0:
                    enc_parts.append((sample_offset, encrypted_size))
                    total_enc_size += encrypted_size
                    sample_offset += encrypted_size
            
            # Concatenate all encrypted bytes for this sample
            all_enc = bytearray()
            for off, size in enc_parts:
                all_enc.extend(mdat_data[off:off + size])
            
            # Decrypt all encrypted bytes at once (single CTR stream)
            all_dec = aes_ctr_decrypt(bytes(all_enc), key_bytes, iv_8)
            
            # Rebuild the sample with clear + decrypted bytes
            dec_offset = 0
            sample_offset = data_offset
            for clear_size, encrypted_size in subsamples:
                if clear_size > 0:
                    result.extend(mdat_data[sample_offset:sample_offset + clear_size])
                    sample_offset += clear_size
                if encrypted_size > 0:
                    result.extend(all_dec[dec_offset:dec_offset + encrypted_size])
                    dec_offset += encrypted_size
                    sample_offset += encrypted_size
            
            data_offset = sample_offset
    
    # Any remaining data
    if data_offset < len(mdat_data):
        result.extend(mdat_data[data_offset:])
    
    return bytes(result)

# ─── Process one file ────────────────────────────────────────────────────
def decrypt_file(input_path, output_path, keys):
    """Decrypt entire MP4 file. keys = {kid_hex: key_hex}
    
    For each moof+mdat pair:
    1. Parse traf for senc (IVs/subsamples) and tenc (KID)
    2. Match KID with provided keys
    3. Decrypt mdat with AES-CTR
    4. Strip encryption boxes (senc/saiz/saio) from moof
    5. Write stripped moof + decrypted mdat
    """
    with open(input_path, 'rb') as f:
        data = f.read()
    
    # Try to find a default KID from moov
    default_kid = find_kid_from_moov(data)
    
    result = bytearray()
    offset = 0
    
    moof_mdat_pairs = []
    
    # First pass: collect all moof+mdat pairs
    while offset < len(data) - 8:
        try:
            box_type, box_offset, box_size, hdr_size = next(
                iter_boxes(data, offset, len(data)), (None, 0, 0, 0)
            )
        except StopIteration:
            break
        if box_type is None:
            break
        
        if box_type == b'moof':
            moof_end = box_offset + box_size
            # Check if next box is mdat
            if moof_end + 8 <= len(data):
                next_size = struct.unpack('>I', data[moof_end:moof_end+4])[0]
                next_type = data[moof_end+4:moof_end+8]
                if next_type == b'mdat':
                    moof_mdat_pairs.append((box_offset, box_size, moof_end, next_size))
                    offset = moof_end + next_size
                    continue
            # moof without mdat - copy as-is
            result.extend(data[box_offset:box_offset + box_size])
            offset = box_offset + box_size
        else:
            # Copy non-moof box as-is
            result.extend(data[box_offset:box_offset + box_size])
            offset = box_offset + box_size
    
    # Second pass: process moof+mdat pairs
    for moof_offset, moof_size, mdat_offset, mdat_size in moof_mdat_pairs:
        moof_data = data[moof_offset:moof_offset + moof_size]
        mdat_data = data[mdat_offset + 8:mdat_offset + mdat_size]  # skip mdat header
        
        # Parse traf inside moof
        samples = None
        track_kid = None
        
        for child_type, child_offset, child_size, child_hdr in iter_boxes(data, moof_offset + 8, moof_offset + moof_size):
            if child_type == b'traf':
                samples, track_kid = parse_traf_for_decrypt(data, child_offset, child_size)
                if samples:
                    break
        
        if not samples:
            # No encryption info - copy as-is
            result.extend(data[moof_offset:mdat_offset + mdat_size])
            continue
        
        # Find the right key
        key_bytes = None
        kid_used = None
        
        if track_kid and track_kid in keys:
            key_bytes = bytes.fromhex(keys[track_kid])
            kid_used = track_kid
        elif default_kid and default_kid in keys:
            key_bytes = bytes.fromhex(keys[default_kid])
            kid_used = default_kid
        else:
            # Try all keys - use first one (last resort)
            for kid, key_hex in keys.items():
                key_bytes = bytes.fromhex(key_hex)
                kid_used = kid
                break
        
        if not key_bytes:
            # No key found - copy as-is
            result.extend(data[moof_offset:mdat_offset + mdat_size])
            continue
        
        # Decrypt
        decrypted_mdat = decrypt_mdat(mdat_data, samples, key_bytes)
        
        # Strip encryption markers from moof
        stripped_moof = strip_moof(data, moof_offset, moof_size)
        
        # Write stripped moof + decrypted mdat
        result.extend(stripped_moof)
        result.extend(struct.pack('>I', mdat_size) + b'mdat')
        result.extend(decrypted_mdat)
    
    with open(output_path, 'wb') as f:
        f.write(result)
    
    return os.path.getsize(output_path)

# ─── CLI ─────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 4:
        print("Usage: python3 mp4decrypt.py --key <kid>:<key> [--key <kid2>:<key2>] ... <input> <output>")
        sys.exit(1)
    
    keys = {}
    args = sys.argv[1:]
    input_file = output_file = None
    
    i = 0
    while i < len(args):
        if args[i] == '--key' and i + 1 < len(args):
            kid, key = args[i+1].split(':', 1)
            keys[kid.lower()] = key.lower()
            i += 2
        else:
            if input_file is None:
                input_file = args[i]
            elif output_file is None:
                output_file = args[i]
            i += 1
    
    if not keys or not input_file or not output_file:
        print("Error: need --key, input, and output")
        sys.exit(1)
    
    print(f"Decrypting: {input_file} -> {output_file}")
    for kid, key in keys.items():
        print(f"  Key: {kid}:{key}")
    
    size = decrypt_file(input_file, output_file, keys)
    print(f"Done! {size} bytes")

if __name__ == "__main__":
    main()
