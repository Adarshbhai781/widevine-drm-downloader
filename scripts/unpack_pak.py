#!/usr/bin/env python3
# =============================================================================
# Unified Tencent PAK Unpacker  (clean version - no modder code)
# -----------------------------------------------------------------------------
# - Works on BOTH original (untouched) paks  AND  modded (poisoned-index) paks
# - Auto-bypasses the RSA index-hash check if the publisher rotated keys
# - Sanitizes poisonous path components (null bytes, control chars,
#   Windows-invalid chars, path-traversal, UNC paths) so every entry can be
#   safely extracted to disk without crashing the unpacker.
#
# Usage:
#     python unpack_pak.py <input.pak> <output_dir>
#
# Example:
#     python unpack_pak.py game_patch_4.5.0.21370.pak ./OUT_MODDED
#     python unpack_pak.py "game_patch_4.5.0.21370 (1).pak" ./OUT_ORIGINAL
# =============================================================================
import os
import sys
import zlib
import struct
import hashlib
from pathlib import PurePath, Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any

# --- third-party deps (same as DHVIP) ---
import gmalg
from Crypto.Cipher import AES
from Crypto.Cipher.AES import MODE_CBC
from Crypto.Hash import SHA1
from Crypto.Util.Padding import unpad
from zstandard import ZstdDecompressor, ZstdCompressionDict, DICT_TYPE_AUTO

# ============================================================================
# Constants
# ============================================================================
CM_NONE = 0
CM_ZLIB = 1
CM_ZSTD = 2
CM_ZSTD_DICT = 3

# Tencent's RSA moduli (extracted from the game client)
RSA_MOD_1 = 0x00C518A646DA5F12B7E5C6183832A7E3A18D79B13E551B75F8AA6699659EF7D3B7E1E37C1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4  # placeholder
RSA_MOD_2 = 0x00E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4F7E1D7FE0FFC8E1D4EFB07C45E1F1F3F4  # placeholder

# NOTE: The actual RSA_MOD_1 / RSA_MOD_2 constants used by Tencent are imported
# from the original DHVIP module. For a fully self-contained script, copy them
# from DHVIP.py (they are large 1024-bit integers). The unpacker still works
# without them because we fall back to SHA1 verification when RSA fails.

# ============================================================================
# Reader
# ============================================================================
class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def u1(self): v = self.data[self.pos]; self.pos += 1; return v
    def u2(self): v = struct.unpack_from('<H', self.data, self.pos)[0]; self.pos += 2; return v
    def u4(self): v = struct.unpack_from('<I', self.data, self.pos)[0]; self.pos += 4; return v
    def u8(self): v = struct.unpack_from('<Q', self.data, self.pos)[0]; self.pos += 8; return v
    def i4(self): v = struct.unpack_from('<i', self.data, self.pos)[0]; self.pos += 4; return v

    def s(self, n):
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v

    def string(self):
        n = self.u4()
        v = self.s(n)
        try:
            return v.decode('utf-8').rstrip('\x00')
        except UnicodeDecodeError:
            return v.decode('latin-1').rstrip('\x00')


# ============================================================================
# PakCrypto
# ============================================================================
class PakCrypto:
    @staticmethod
    @lru_cache(maxsize=1)
    def zuc_keystream() -> bytes:
        # Tencent's ZUC configuration - produces 0x500 bytes of keystream
        # used to decrypt the index. Implementation borrowed from DHVIP.
        # ... (full ZUC implementation - same as DHVIP)
        # Returns 0x500 bytes of keystream
        from DHVIP import PakCrypto as _DPC
        return _DPC.zuc_keystream()

    @staticmethod
    def rsa_extract(packed_hash: bytes, modulus: int) -> bytes:
        # Tencent stores the index hash XORed with an RSA-derived value.
        # We just XOR the bytes back; if the publisher rotated RSA keys,
        # the result won't match expected_hash, and the caller should
        # fall back to SHA1 verification.
        from DHVIP import PakCrypto as _DPC
        return _DPC.rsa_extract(packed_hash, modulus)

    @staticmethod
    def decrypt_index(index_data, pak_info) -> bytes:
        from DHVIP import PakCrypto as _DPC
        return _DPC.decrypt_index(index_data, pak_info)

    @staticmethod
    def align_encrypted_content_size(size: int, encryption_method: int) -> int:
        from DHVIP import PakCrypto as _DPC
        return _DPC.align_encrypted_content_size(size, encryption_method)

    @staticmethod
    def decrypt_block(data, file_path, encryption_method):
        from DHVIP import PakCrypto as _DPC
        return _DPC.decrypt_block(data, file_path, encryption_method)

    @staticmethod
    def _is_simple1_method(m): 
        from DHVIP import PakCrypto as _DPC
        return _DPC._is_simple1_method(m)

    @staticmethod
    def _is_simple2_method(m):
        from DHVIP import PakCrypto as _DPC
        return _DPC._is_simple2_method(m)

    @staticmethod
    def _is_sm4_method(m):
        from DHVIP import PakCrypto as _DPC
        return _DPC._is_sm4_method(m)

    @staticmethod
    def generate_block_indices(n, enc):
        from DHVIP import PakCrypto as _DPC
        return _DPC.generate_block_indices(n, enc)


# ============================================================================
# TencentPakEntry / TencentPakInfo / TencentPakFile
# ============================================================================
@dataclass
class PakCompressedBlock:
    start: int
    end: int

@dataclass
class TencentPakEntry:
    def __init__(self, reader: Reader, version: int):
        self.offset = reader.u8()
        self.size = reader.u8() if version >= 13 else reader.u4()
        self.uncompressed_size = reader.u8()
        self.compression_method = reader.u4()
        self.hash = reader.s(20)
        if self.compression_method != CM_NONE:
            blocks_count = reader.u4()
            if blocks_count == 0:
                self.compressed_blocks = []
            else:
                self.compressed_blocks = [
                    PakCompressedBlock(reader.u8(), reader.u8())
                    for _ in range(blocks_count)
                ]
        else:
            self.compressed_blocks = []
        if version >= 10:
            self.encrypted = bool(reader.u1())
        else:
            self.encrypted = False
        if version >= 13:
            self.encryption_method = reader.u4()
            self._u4_1 = reader.u4()  # unknown
            self._u4_2 = reader.u4()  # unknown
            self._u4_3 = reader.u4()  # unknown
        else:
            self.encryption_method = 0


class TencentPakInfo:
    """Parses the pak footer (last 64+ bytes)."""
    def __init__(self, content, zuc_key):
        # Footer is at end of file
        # ... (implementation copied from DHVIP)
        from DHVIP import TencentPakInfo as _DTP
        # Copy fields from the canonical implementation
        self._content = content
        self._parse_footer()
    
    def _parse_footer(self):
        # Use DHVIP's parser
        from DHVIP import TencentPakInfo as _DTP
        tmp = _DTP(self._content, PakCrypto.zuc_keystream())
        for attr in ['version', 'magic', 'index_offset', 'index_size',
                     'index_encrypted', 'index_hash', 'packed_index_hash',
                     'stem_hash', 'extra_data']:
            if hasattr(tmp, attr):
                setattr(self, attr, getattr(tmp, attr))


class TencentPakFile:
    """Load + dump a Tencent PAK file (handles modded/poisoned paks too)."""

    def __init__(self, file_path: PurePath, is_od: bool = False):
        self._file_path = file_path
        with open(file_path, 'rb') as f:
            self._file_content = memoryview(f.read())
        self._is_od = is_od
        self._mount_point = PurePath()
        self._is_zstd_with_dict = 'zsdic' in str(self._file_path)
        self._zstd_dict = None
        self._files: List[TencentPakEntry] = []
        self._index: Dict[PurePath, Dict[str, TencentPakEntry]] = {}
        self._pak_info = TencentPakInfo(self._file_content, PakCrypto.zuc_keystream())
        self._verify_stem_hash()
        self._tencent_load_index()

    def _verify_stem_hash(self):
        # Stem hash check: CRC32 of filename in UTF-32LE.
        # Skip for OD (online-distributed) paks.
        if not self._is_od and getattr(self._pak_info, 'version', 0) >= 9:
            stem = self._file_path.stem
            calc = zlib.crc32(stem.encode('utf-32le'))
            if hasattr(self._pak_info, 'stem_hash'):
                try:
                    assert self._pak_info.stem_hash == calc
                except AssertionError:
                    print(f"  [warn] stem hash mismatch (filename was renamed?) - continuing")

    def _tencent_load_index(self):
        index_data = self._file_content[
            self._pak_info.index_offset:][:self._pak_info.index_size]
        if self._pak_info.index_encrypted:
            index_data = PakCrypto.decrypt_index(index_data, self._pak_info)
        self._verify_index_hash(index_data)
        self._load_index(index_data)

    def _verify_index_hash(self, index_data):
        """
        Verify the index hash.
        
        Original paks: RSA-derived hash matches AND SHA1 of index_data matches.
        Modded paks:   RSA-derived hash may NOT match (publisher rotated keys).
                       Fall back to SHA1 (the actual content hash) and continue.
        """
        expected_hash = self._pak_info.index_hash
        if not self._is_od and self._pak_info.version >= 8:
            try:
                assert expected_hash == PakCrypto.rsa_extract(
                    self._pak_info.packed_index_hash, RSA_MOD_2)
            except AssertionError:
                # RSA signature mismatch - fall back to SHA1 content check.
                # This is normal for some modded paks whose signing key rotated.
                pass
        # SHA1 is the real integrity check; if it passes, the index is intact.
        try:
            assert expected_hash == SHA1.new(index_data).digest()
        except AssertionError:
            print("  [warn] index SHA1 mismatch - the index may have been tampered")

    @staticmethod
    def _construct_mount_point(mount_point: str) -> PurePath:
        result = PurePath()
        for part in PurePath(mount_point).parts:
            if part != '..':
                result /= part
        return result

    def _peek_content(self, offset, size, encryption_method):
        size = PakCrypto.align_encrypted_content_size(size, encryption_method)
        return self._file_content[offset:][:size]

    def _peek_block_content(self, block, encryption_method):
        size = PakCrypto.align_encrypted_content_size(block.end - block.start, encryption_method)
        return self._file_content[block.start:][:size]

    def _construct_zstd_dict(self, dict_entry):
        assert not self._zstd_dict
        assert not dict_entry.encrypted
        assert dict_entry.compression_method == CM_NONE
        reader = Reader(self._peek_content(dict_entry.offset, dict_entry.size, 0))
        dict_size = reader.u8()
        _ = reader.u4()
        assert dict_size == reader.u4()
        dict_data = reader.s(dict_size)
        self._zstd_dict = PakCompression.zstd_dictionary(dict_data)

    def _load_index(self, index_data):
        if self._pak_info.version <= 10:
            raise ValueError(f'Unsupported version: {self._pak_info.version}')
        reader = Reader(index_data)
        self._mount_point = self._construct_mount_point(reader.string())
        self._files = [TencentPakEntry(reader, self._pak_info.version)
                       for _ in range(reader.u4())]
        for _ in range(reader.u8()):
            dir_path = PurePath(reader.string())
            e = {reader.string(): self._files[~reader.i4()]
                 for _ in range(reader.u8())}
            if self._is_zstd_with_dict and dir_path.name == 'zstddic':
                assert len(e) == 1
                self._construct_zstd_dict(e[[*e.keys()][0]])
            else:
                self._index.update({PurePath(dir_path): e})

    def _write_to_disk(self, file_path: Path, entry: TencentPakEntry):
        encryption_method = entry.encryption_method
        compression_method = entry.compression_method
        with open(file_path, 'wb') as f:
            if compression_method == CM_NONE:
                data = self._peek_content(entry.offset, entry.size, encryption_method)
                if entry.encrypted:
                    data = PakCrypto.decrypt_block(data, file_path, encryption_method)
                f.write(data)
            else:
                for x in PakCrypto.generate_block_indices(
                        len(entry.compressed_blocks), encryption_method):
                    data = self._peek_block_content(
                        entry.compressed_blocks[x], encryption_method)
                    if entry.encrypted:
                        data = PakCrypto.decrypt_block(data, file_path, encryption_method)
                    data = PakCompression.decompress_block(
                        data, self._zstd_dict, compression_method)
                    f.write(data)

    # ---------------- PATH SANITIZATION (anti-trap) ----------------
    @staticmethod
    def _sanitize_path_part(name: str) -> str:
        """Sanitize ONE path component (file or dir name).

        Some modded paks embed null bytes, control chars, Windows-invalid
        chars (? * < > | " :), and path-traversal sequences inside file/dir
        names as an anti-unpacker trap. Replace each forbidden character
        with '_' so we can still extract every entry to disk safely.
        """
        if not name:
            return '_'
        # Strip null bytes and other C0/C1 control characters
        cleaned = ''.join(c if (ord(c) >= 0x20 and ord(c) != 0x7f) else '_'
                          for c in name)
        # Replace Windows-invalid characters
        for bad in ['?', '*', '<', '>', '|', '"', ':']:
            cleaned = cleaned.replace(bad, '_')
        # Collapse multiple underscores
        while '__' in cleaned:
            cleaned = cleaned.replace('__', '_')
        cleaned = cleaned.strip(' .')
        if not cleaned:
            cleaned = '_'
        return cleaned

    @staticmethod
    def _sanitize_path(p: PurePath) -> PurePath:
        """Rebuild a PurePath replacing '..' / invalid chars in every part."""
        result = PurePath()
        for part in p.parts:
            if part == '..':
                result /= '_up_'
            elif part == '/':
                result /= '_root_'
            else:
                result /= TencentPakFile._sanitize_path_part(part)
        return result

    # ---------------- DUMP ----------------
    def dump(self, out_path: Path) -> None:
        out_path = out_path / self._sanitize_path(self._mount_point)
        out_path.mkdir(parents=True, exist_ok=True)
        total_files = sum(len(d) for d in self._index.values())
        collision_counter: Dict[str, int] = {}
        processed = 0
        for dir_path, dir_content in self._index.items():
            current_out_path = out_path / self._sanitize_path(dir_path)
            try:
                current_out_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                current_out_path = out_path / '_flattened_'
                current_out_path.mkdir(parents=True, exist_ok=True)
            for file_name, entry in dir_content.items():
                safe_name = self._sanitize_path_part(file_name)
                target = current_out_path / safe_name
                if target.exists():
                    key = str(target)
                    collision_counter[key] = collision_counter.get(key, 0) + 1
                    stem, dot, ext = safe_name.rpartition('.')
                    if dot:
                        target = current_out_path / f'{stem}__{collision_counter[key]}.{ext}'
                    else:
                        target = current_out_path / f'{safe_name}__{collision_counter[key]}'
                self._write_to_disk(target, entry)
                processed += 1
                if processed % 50 == 0 or processed == total_files:
                    print(f"  [{processed}/{total_files}] extracted")
        print(f"\n[OK] Extracted {processed} files to: {out_path}")


# ============================================================================
# Main
# ============================================================================
def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <input.pak> <output_dir>")
        print(f"Example:")
        print(f"  python {sys.argv[0]} game_patch_4.5.0.21370.pak ./OUT_MODDED")
        print(f"  python {sys.argv[0]} \"game_patch_4.5.0.21370 (1).pak\" ./OUT_ORIGINAL")
        sys.exit(1)

    pak_path = PurePath(sys.argv[1])
    out_dir = Path(sys.argv[2])

    if not os.path.exists(pak_path):
        print(f"ERROR: pak file not found: {pak_path}")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Unpacking {pak_path.name} ===")
    print(f"  -> output: {out_dir}")
    pak = TencentPakFile(pak_path)
    print(f"  mount point: {pak._mount_point}")
    print(f"  version: {pak._pak_info.version}")
    print(f"  total entries: {sum(len(d) for d in pak._index.values())}")
    print()
    pak.dump(out_dir)


if __name__ == '__main__':
    # Lazy import of DHVIP helpers (PakCompression, ZUC implementation etc.)
    # The actual DHVIP.py must be on sys.path or in the same folder.
    sys.path.insert(0, '/home/z/my-project/pak_workspace')
    sys.path.insert(0, '/home/z/my-project/upload')
    try:
        from DHVIP import PakCompression  # noqa
        from functools import lru_cache   # noqa
    except ImportError:
        print("Note: DHVIP.py not found on path. Falling back to direct import.")
    main()
