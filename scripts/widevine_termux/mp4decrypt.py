#!/usr/bin/env python3
"""
Python mp4decrypt - Properly decrypt CENC encrypted MP4/DASH segments
=====================================================================
Correctly parses moof/traf/senc boxes for per-sample IVs and subsamples,
then decrypts mdat using AES-CTR.

Usage:
    python3 mp4decrypt.py --key <kid>:<key> <input.mp4> <output.mp4>
"""

import sys
import os
import struct
import io

# ─── AES-CTR ──────────────────────────────────────────────────────────────
def aes_ctr_decrypt(data, key_bytes, iv_8):
    """Decrypt with AES-CTR. IV is 8 bytes, extended to 16 with trailing zeros.
    
    Per ISO 23001-7 (CENC), the 8-byte IV is placed in the first 8 bytes
    of the 16-byte CTR IV, with the remaining 8 bytes set to zero.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    iv_16 = iv_8 + b'\x00' * 8  # CENC: IV is left-aligned, right-padded with zeros
    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(iv_16))
    dec = cipher.decryptor()
    return dec.update(data) + dec.finalize()

# ─── MP4 Box Iterator ────────────────────────────────────────────────────
def iter_boxes(data, start=0, end=None):
    """Yield (box_type, box_offset, box_size, header_size) for top-level boxes."""
    if end is None:
        end = len(data)
    offset = start
    while offset < end - 8:
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

# ─── Parse senc ──────────────────────────────────────────────────────────
def parse_senc(data, offset, size):
    """Parse a senc box. Returns list of (iv_8bytes, [(clear, encrypted), ...])."""
    header_size = 8
    version = data[offset + header_size]
    flags = (data[offset+9] << 16) | (data[offset+10] << 8) | data[offset+11]
    has_subsamples = bool(flags & 0x02) or bool(flags & 0x01)  # either flag means subsamples
    
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
        
        # Use only first 8 bytes of IV regardless
        iv_8 = iv[:8] if len(iv) >= 8 else iv
        samples.append((iv_8, subsamples))
    
    return samples

# ─── Parse traf ──────────────────────────────────────────────────────────
def parse_traf(data, traf_offset, traf_size):
    """Parse traf box to extract encryption info from senc."""
    traf_end = traf_offset + traf_size
    
    for box_type, box_offset, box_size, hdr_size in iter_boxes(data, traf_offset + 8, traf_end):
        if box_type == b'senc':
            return parse_senc(data, box_offset, box_size)
    
    return None

# ─── Decrypt mdat using sample info ──────────────────────────────────────
def decrypt_mdat(mdat_data, samples, key_bytes):
    """Decrypt mdat content using per-sample IVs and subsample patterns.
    
    IMPORTANT: In CENC AES-CTR, all encrypted portions within a single sample
    share the same CTR counter stream. So we must concatenate all encrypted
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
            # First pass: collect clear and encrypted byte ranges
            clear_parts = []  # (offset_in_mdat, size)
            enc_parts = []    # (offset_in_mdat, size)
            total_enc_size = 0
            
            sample_offset = data_offset
            for clear_size, encrypted_size in subsamples:
                if clear_size > 0:
                    clear_parts.append((sample_offset, clear_size))
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
            
            # Second pass: rebuild the sample with clear + decrypted bytes
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
    
    # Any remaining data (shouldn't happen normally)
    if data_offset < len(mdat_data):
        result.extend(mdat_data[data_offset:])
    
    return bytes(result)

# ─── Process one file ────────────────────────────────────────────────────
def decrypt_file(input_path, output_path, keys):
    """Decrypt entire MP4 file. keys = {kid_hex: key_hex}"""
    with open(input_path, 'rb') as f:
        data = f.read()
    
    result = bytearray()
    offset = 0
    
    while offset < len(data) - 8:
        box_type, box_offset, box_size, hdr_size = next(
            iter_boxes(data, offset, len(data)), (None, 0, 0, 0)
        )
        if box_type is None:
            break
        
        if box_type == b'moof':
            # Parse moof to get encryption info
            moof_end = box_offset + box_size
            
            # Find traf inside moof
            samples = None
            for child_type, child_offset, child_size, child_hdr in iter_boxes(data, box_offset + 8, moof_end):
                if child_type == b'traf':
                    samples = parse_traf(data, child_offset, child_size)
                    if samples:
                        break
            
            # Check if next box is mdat
            mdat_offset = moof_end
            if mdat_offset + 8 <= len(data):
                mdat_size = struct.unpack('>I', data[mdat_offset:mdat_offset+4])[0]
                mdat_type = data[mdat_offset+4:mdat_offset+8]
            else:
                mdat_size = 0
                mdat_type = b''
            
            if samples and mdat_type == b'mdat':
                # We have encryption info + mdat - decrypt it
                mdat_data = data[mdat_offset+8:mdat_offset+mdat_size]
                
                # Get key (use first key for now - proper impl would match KID from tfhd)
                key_hex = list(keys.values())[0]
                key_bytes = bytes.fromhex(key_hex)
                
                # Decrypt
                decrypted_mdat = decrypt_mdat(mdat_data, samples, key_bytes)
                
                # Write moof + decrypted mdat
                result.extend(data[box_offset:moof_end])
                result.extend(struct.pack('>I', mdat_size) + b'mdat')
                result.extend(decrypted_mdat)
                
                offset = mdat_offset + mdat_size
            else:
                # No encryption or no mdat - copy as-is
                if mdat_type == b'mdat':
                    result.extend(data[box_offset:mdat_offset + mdat_size])
                    offset = mdat_offset + mdat_size
                else:
                    result.extend(data[box_offset:moof_end])
                    offset = moof_end
        else:
            # Copy box as-is
            result.extend(data[box_offset:box_offset + box_size])
            offset = box_offset + box_size
    
    with open(output_path, 'wb') as f:
        f.write(result)
    
    return os.path.getsize(output_path)

# ─── CLI ─────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 4:
        print("Usage: python3 mp4decrypt.py --key <kid>:<key> <input> <output>")
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
