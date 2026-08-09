"""Standalone PAK parser - extracted from DHVIP tool for comparison purposes."""
import struct
import math
import zlib
import sys
import itertools as it
import hashlib
from pathlib import PurePath, Path
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

# Import gmalg for ZUC keystream
import gmalg
from Crypto.Cipher import AES
from Crypto.Cipher.AES import MODE_CBC
from Crypto.Hash import SHA1
from Crypto.Util.Padding import unpad
from zstandard import ZstdDecompressor, ZstdCompressionDict, DICT_TYPE_AUTO, ZstdCompressor

# === Constants from DHVIP ===
ZUC_KEY = bytes.fromhex('01010101010101010101010101010101')
ZUC_IV = bytes.fromhex('FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF')

RSA_MOD_1 = bytes.fromhex('CBE8B9F2504050EF9831B719E9A6249A6D238505ADE909BDE78C180DED6072A0C3347B8AF4780E1F212D952D82D4BF7F233C1ECA499E1F9D9A85B4FAD759F54BABC1666C5DE411EA9E4B2374425DD6C6F54333BBC8F2610FE6063E4D0D6C21A671A8F7C3740555E5DC06D4E1691C456DB4116C0C012BF7B206E8311AAAEC689952BF804EF638F09D5822B4117B114208F14DEB459E80CB770E5B0D7978E21F5E6CED4999D3583108221A7AB28B960277ADB5690A332784019D9C195BE4EA9EA0A09459010F236465DE0D59C3EF7324E954E1118D93EE19F299760C2CDB963CE87973EA5ECC9BBE81C27D4C7C8572AC07E9BCEAC9BD72AB7A56A3C0AD736ABCE4')
RSA_MOD_2 = bytes.fromhex('7F58E8A39A4DA4E87357DDD650EAA16D3B5CE95B213D1030A662566444796A78A84AE9AC3DBFFDE7F41094896696835DAF13B89E6EC2B84963B1B1BAF7151DA245C3FBFAE2A6AE18B2684D03F9229DE2C91440F2A3A3BCDE1E5680C16722A88039C73560D5D43F4B6562C2EEA5B1D926D86B51108A2643C70FB74D6442CE3A08339B8FD8F660AE88129B7AB8C46F2FA58124485CCCB1E987B05A6DA65A01858ED3F89905449AE42BB07290FCB9994BF22E26610BCABB9804783A3B9587917F3D97316EDDA15C5E13F79066407B55A93B291B68A4AC42A98D6E35FED84B14A792D154E62028DDAD20FC301951E5924BE9AD62FB719DD94CC30CAB871BEC4377A8')

SIMPLE1_DECRYPT_KEY = 121
SIMPLE2_DECRYPT_KEY = bytes.fromhex('E55B4ED1')
SIMPLE2_BLOCK_SIZE = 16

SM4_SECRET_4 = 'eb691efea914241317a8'
SM4_SECRET_2 = 'Q0hVTKey$as*1ZFlQCiA'
SM4_SECRET_NEW = [
    'xG2qW5lP7lV2iN5fN5pG', 'xT1cJ6dL5wC0kK1rB4dK',
    'qC4jS5bZ6fL5xE6nD4zA', 'gD4jQ2aL3bS3lC3xT0iW',
    'xU1yQ8wE9zY3gZ3bT5aE', 'uQ3cO2dX7xY4xU7gH7iS',
    'gW1fR0jK6wQ4oN0oK1kZ', 'aJ4pV7iZ7pU4wP2aC2cZ',
    'cX6jT3cM2oT3vK0kJ1qN', 'iT2vS0cS6yT6cZ1sE1lO',
    'hM1pH9iY8wM9hT4lN5uJ', 'kG6bC8jK0fL0dE4sH4mL',
    'dB6lB3vE0eZ8wM8rI0aC', 'tP7sP7nI9rA2vQ4cV5yQ',
    'aT0cL1yN4pT3sZ7eM2vY', 'uV6fU8fC9zN3mP5dH8mN'
]

EM_SIMPLE1 = 1
EM_SIMPLE2 = 16
EM_SM4_2 = 2
EM_SM4_4 = 4
EM_SM4_NEW_BASE = 31
EM_SM4_NEW_MASK = ~EM_SM4_NEW_BASE
EM_UNKNOWN_17 = 17

CM_NONE = 0
CM_ZLIB = 1
CM_ZSTD = 6
CM_ZSTD_DICT = 8
CM_MASK = 15

# === SM4 Implementation ===
class SM4:
    _S_BOX = bytes([
        52, 102, 37, 116, 137, 120, 228, 169, 90, 65, 188, 122, 214, 22, 33, 35,
        77, 97, 218, 148, 155, 223, 19, 60, 105, 58, 49, 10, 95, 215, 153, 149,
        241, 174, 114, 61, 7, 96, 36, 182, 152, 238, 196, 162, 45, 136, 221, 141,
        4, 234, 187, 17, 202, 62, 93, 161, 246, 63, 176, 151, 128, 71, 43, 166,
        230, 247, 217, 177, 89, 192, 124, 190, 84, 40, 183, 126, 79, 248, 67, 110,
        160, 80, 14, 245, 144, 184, 251, 163, 123, 98, 25, 70, 3, 42, 185, 143,
        159, 119, 180, 91, 131, 135, 8, 235, 226, 30, 66, 240, 15, 232, 113, 106,
        117, 173, 85, 31, 181, 171, 51, 250, 127, 21, 189, 133, 216, 6, 104, 179,
        82, 48, 72, 11, 0, 237, 239, 178, 87, 142, 231, 108, 213, 229, 46, 83,
        130, 5, 249, 129, 244, 86, 191, 140, 75, 227, 219, 74, 145, 76, 44, 211,
        64, 41, 78, 32, 20, 54, 121, 9, 111, 209, 55, 224, 57, 12, 138, 146,
        56, 18, 53, 109, 225, 253, 147, 154, 23, 212, 201, 156, 107, 132, 38, 157,
        168, 15, 101, 199, 162, 214, 249, 115, 239, 2, 103, 69, 150, 216, 46, 175,
        10, 197, 222, 173, 194, 213, 127, 145, 208, 206, 238, 250, 118, 200, 235,
        1, 112, 81, 220, 179, 49, 44, 96, 183, 240, 125, 27, 246, 11, 232, 163,
        227, 155, 13, 88, 34, 198, 186, 161, 94, 156, 57, 216, 140, 237, 153, 141,
    ])
    _CK = [0x00070E15, 0x1C232A31, 0x383F464D, 0x545B6269,
           0x70777E85, 0x8C939AA1, 0xA8AFB6BD, 0xC4CBD2D9,
           0xE0E7EEF1, 0xFC030A11, 0x181F262D, 0x343B4249,
           0x50575E65, 0x6C737A81, 0x888F969D, 0xA4ABB2B9,
           0xC0C7CED5, 0xDCE3EAF1, 0xF8FF060D, 0x141B2229,
           0x30373E45, 0x4C535A61, 0x686F767D, 0x848B9299,
           0xA0A7AEB5, 0xBCC3CAD1, 0xD8DFE6ED, 0xF4FB0209,
           0x10171E25, 0x2C333A41, 0x484F565D, 0x646B7279]
    _FK = [0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC]

    @staticmethod
    def _rotl32(x, n):
        return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF

    @staticmethod
    def _key_expand(key: bytes, rkey: list):
        K0 = int.from_bytes(key[0:4], 'big') ^ SM4._FK[0]
        K1 = int.from_bytes(key[4:8], 'big') ^ SM4._FK[1]
        K2 = int.from_bytes(key[8:12], 'big') ^ SM4._FK[2]
        K3 = int.from_bytes(key[12:16], 'big') ^ SM4._FK[3]
        rk = rkey
        for i in range(32):
            rk[i] = K0
            rk[i + 1] = K1
            rk[i + 2] = K2
            rk[i + 3] = K3
            T = K0 ^ SM4._rotl32(K1 ^ K2 ^ K3 ^ SM4._CK[i], 13)
            T = SM4._S_BOX[(T >> 24) & 0xFF] << 24 | SM4._S_BOX[(T >> 16) & 0xFF] << 16 | SM4._S_BOX[(T >> 8) & 0xFF] << 8 | SM4._S_BOX[T & 0xFF]
            T ^= SM4._rotl32(T, 7) ^ SM4._rotl32(T, 23)
            K0 = K1 ^ T; K1 = K2 ^ T; K2 = K3 ^ T; K3 = K0

    @classmethod
    def key_length(cls):
        return 16

    @classmethod
    def block_length(cls):
        return 16

    def __init__(self, key: bytes):
        if len(key) != self.key_length():
            raise ValueError(f'Key must be {self.key_length()} bytes')
        self._key = key
        self._rkey = [0] * 32
        SM4._key_expand(self._key, self._rkey)
        self._block_buffer = bytearray()

    def encrypt(self, block: bytes) -> bytes:
        if len(block) != self.block_length():
            raise ValueError(f'Block must be {self.block_length()} bytes')
        RK = self._rkey
        X0 = int.from_bytes(block[0:4], 'big')
        X1 = int.from_bytes(block[4:8], 'big')
        X2 = int.from_bytes(block[8:12], 'big')
        X3 = int.from_bytes(block[12:16], 'big')
        for i in range(32):
            T = X0 ^ RK[i]
            T = SM4._rotl32(T, 2) ^ SM4._rotl32(T, 10) ^ SM4._rotl32(T, 18) ^ SM4._rotl32(T, 24)
            T = SM4._S_BOX[(T >> 24) & 0xFF] << 24 | SM4._S_BOX[(T >> 16) & 0xFF] << 16 | SM4._S_BOX[(T >> 8) & 0xFF] << 8 | SM4._S_BOX[T & 0xFF]
            T ^= RK[i + 1] if i % 2 else RK[i + 3]
            X0, X1, X2, X3 = X1, X2, X3, T
        BUFFER = self._block_buffer
        BUFFER.clear()
        for x in (X3, X2, X1, X0):
            BUFFER.extend(x.to_bytes(4, 'big'))
        return bytes(BUFFER)

    def decrypt(self, block: bytes) -> bytes:
        if len(block) != self.block_length():
            raise ValueError(f'Block must be {self.block_length()} bytes')
        RK = self._rkey
        X0 = int.from_bytes(block[0:4], 'big')
        X1 = int.from_bytes(block[4:8], 'big')
        X2 = int.from_bytes(block[8:12], 'big')
        X3 = int.from_bytes(block[12:16], 'big')
        for i in range(31, -1, -1):
            T = X0 ^ RK[i]
            T = SM4._rotl32(T, 2) ^ SM4._rotl32(T, 10) ^ SM4._rotl32(T, 18) ^ SM4._rotl32(T, 24)
            T = SM4._S_BOX[(T >> 24) & 0xFF] << 24 | SM4._S_BOX[(T >> 16) & 0xFF] << 16 | SM4._S_BOX[(T >> 8) & 0xFF] << 8 | SM4._S_BOX[T & 0xFF]
            T ^= RK[i + 1] if i % 2 else RK[i + 3]
            X0, X1, X2, X3 = X1, X2, X3, T
        BUFFER = self._block_buffer
        BUFFER.clear()
        for x in (X3, X2, X1, X0):
            BUFFER.extend(x.to_bytes(4, 'big'))
        return bytes(BUFFER)

# === Reader ===
class Reader:
    def __init__(self, buffer, offset=0):
        self._buffer = buffer
        self._cursor = offset

    def u1(self, move_cursor=True) -> int:
        return self.unpack('B', move_cursor=move_cursor)[0]
    def u4(self, move_cursor=True) -> int:
        return self.unpack('<I', move_cursor=move_cursor)[0]
    def u8(self, move_cursor=True) -> int:
        return self.unpack('<Q', move_cursor=move_cursor)[0]
    def i4(self, move_cursor=True) -> int:
        return self.unpack('<i', move_cursor=move_cursor)[0]
    def i8(self, move_cursor=True) -> int:
        return self.unpack('<q', move_cursor=move_cursor)[0]
    def s(self, n: int, move_cursor=True) -> bytes:
        return self.unpack(f'{n}s', move_cursor=move_cursor)[0]
    def unpack(self, f: str, offset=0, move_cursor=True):
        x = struct.unpack_from(f, self._buffer, self._cursor + offset)
        if move_cursor:
            self._cursor += struct.calcsize(f)
        return x
    def string(self, move_cursor=True) -> str:
        length = self.i4(move_cursor=move_cursor)
        if length == 0:
            return str()
        else:
            assert length > 0
            offset = 0 if move_cursor else 4
            return self.unpack(f'{length}s', offset=offset, move_cursor=move_cursor)[0].rstrip(b'\x00').decode()

# === PakInfo ===
class PakInfo:
    def __init__(self, buffer, keystream: List[int]):
        def decrypt_index_encrypted(x: int) -> int:
            MASK_8 = 255
            return (x ^ keystream[3]) & MASK_8
        def decrypt_magic(x: int) -> int:
            return x ^ keystream[2]
        def decrypt_index_hash(x: bytes) -> bytes:
            key = struct.pack('<5I', *keystream[4:][:5])
            assert len(x) == len(key)
            return bytes((a ^ b for a, b in zip(x, key)))
        def decrypt_index_size(x: int) -> int:
            return x ^ (keystream[10] << 32 | keystream[11])
        def decrypt_index_offset(x: int) -> int:
            return x ^ (keystream[0] << 32 | keystream[1])
        reader = Reader(buffer[-PakInfo._mem_size((-1)):])
        self.index_encrypted = decrypt_index_encrypted(reader.u1()) == 1
        self.magic = decrypt_magic(reader.u4())
        self.version = reader.u4()
        self.index_hash = decrypt_index_hash(reader.s(20)) if self.version >= 6 else bytes()
        self.index_size = decrypt_index_size(reader.u8())
        self.index_offset = decrypt_index_offset(reader.u8())
        if self.version <= 3:
            self.index_encrypted = False
    @staticmethod
    def _mem_size(_: int) -> int:
        return 45

class TencentPakInfo(PakInfo):
    def __init__(self, buffer, keystream: List[int]):
        def decrypt_unk(x: bytes) -> bytes:
            key = struct.pack('<8I', *keystream[7:][:8])
            assert len(x) == len(key)
            return bytes((a ^ b for a, b in zip(x, key)))
        def decrypt_stem_hash(x: int) -> int:
            return x ^ keystream[8]
        def decrypt_unk_hash(x: int) -> int:
            return x ^ keystream[9]
        super().__init__(buffer, keystream)
        reader = Reader(buffer[-TencentPakInfo._mem_size(self.version):])
        self.unk1 = decrypt_unk(reader.s(32)) if self.version >= 7 else bytes()
        self.packed_key = reader.s(256) if self.version >= 8 else bytes()
        self.packed_iv = reader.s(256) if self.version >= 8 else bytes()
        self.packed_index_hash = reader.s(256) if self.version >= 8 else bytes()
        self.stem_hash = decrypt_stem_hash(reader.u4()) if self.version >= 9 else 0
        self.unk2 = decrypt_unk_hash(reader.u4()) if self.version >= 9 else 0
        self.content_org_hash = reader.s(20) if self.version >= 12 else bytes()
    @staticmethod
    def _mem_size(version: int) -> int:
        size_for_7 = 32 if version >= 7 else 0
        size_for_8 = 768 if version >= 8 else 0
        size_for_9 = 8 if version >= 9 else 0
        size_for_12 = 20 if version >= 12 else 0
        return PakInfo._mem_size(version) + size_for_7 + size_for_8 + size_for_9 + size_for_12

class PakCompressedBlock:
    def __init__(self, reader: Reader):
        self.start = reader.u8()
        self.end = reader.u8()

class TencentPakEntry:
    def __init__(self, reader: Reader, version: int):
        self.content_hash = reader.s(20)
        if version <= 1:
            _ = reader.u8()
        self.offset = reader.u8()
        self.uncompressed_size = reader.u8()
        self.compression_method = reader.u4() & CM_MASK
        self.size = reader.u8()
        self.unk1 = reader.u1() if version >= 5 else 0
        self.unk2 = reader.s(20) if version >= 5 else bytes()
        if self.compression_method != 0 and version >= 3:
            self.compressed_blocks = [PakCompressedBlock(reader) for _ in range(reader.u4())]
        else:
            self.compressed_blocks = []
        self.compression_block_size = reader.u4() if version >= 4 else 0
        self.encrypted = reader.u1() == 1 if version >= 4 else False
        self.encryption_method = reader.u4() if version >= 12 else 0
        self.index_new_sep = reader.u4() if version >= 12 else 0

# === Misc ===
class Misc:
    @staticmethod
    def pad_to_n(data: bytes, n: int) -> bytes:
        assert n > 0
        padding = n - len(data) % n
        if padding == n:
            return data
        else:
            return data + b'\x00' * padding

# === PakCrypto ===
class PakCrypto:
    @staticmethod
    def zuc_keystream() -> List[int]:
        zuc = gmalg.ZUC(ZUC_KEY, ZUC_IV)
        return [struct.unpack('>I', zuc.generate())[0] for _ in range(16)]

    @staticmethod
    def _xorxor(buffer, x) -> bytes:
        return bytes((buffer[i] ^ x[i % len(x)] for i in range(len(buffer))))

    @staticmethod
    def _hashhash(buffer, n: int) -> bytes:
        result = bytes()
        for i in range(math.ceil(n / SHA1.digest_size)):
            result += SHA1.new(buffer).digest()
        if len(result) >= n:
            result = result[:n]
            return result
        else:
            result += b'\x00' * (n - len(result))
            return result

    @staticmethod
    def _meowmeow(buffer) -> bytes:
        def unpad(x):
            skip = 1 + next((i for i in range(len(x)) if x[i] != 0))
            return x[skip:]
        if len(buffer) < 43:
            return bytes()
        else:
            x1 = buffer[1:][:SHA1.digest_size]
            x2 = buffer[SHA1.digest_size + 1:]
            x1 = PakCrypto._xorxor(x1, PakCrypto._hashhash(x2, len(x1)))
            x2 = PakCrypto._xorxor(x2, PakCrypto._hashhash(x1, len(x2)))
            part1, m = (x2[:SHA1.digest_size], x2[SHA1.digest_size:])
            if part1 != SHA1.new(b'\x00' * SHA1.digest_size).digest():
                return bytes()
            else:
                return unpad(m)

    @staticmethod
    def rsa_extract(signature: bytes, modulus: bytes) -> bytes:
        c = int.from_bytes(signature, 'little')
        n = int.from_bytes(modulus, 'little')
        e = 65537
        m = pow(c, e, n).to_bytes(256, 'little').rstrip(b'\x00')
        return PakCrypto._meowmeow(Misc.pad_to_n(m, 4))

    @staticmethod
    def _decrypt_simple1(ciphertext) -> bytes:
        return bytes((x ^ SIMPLE1_DECRYPT_KEY for x in ciphertext))

    @staticmethod
    def decrypt_index(ciphertext, pak_info):
        # Try RSA -> AES-CBC first
        try:
            key_material = PakCrypto.rsa_extract(pak_info.packed_key, RSA_MOD_1)
            if len(key_material) >= 48:
                key = key_material[:32]
                iv = key_material[32:]
                if len(iv) < 16:
                    iv = iv.ljust(16, b'\x00')
                aes = AES.new(key[:16], MODE_CBC, iv[:16])
                decrypted = unpad(aes.decrypt(ciphertext), AES.block_size)
                # Validate: first 4 bytes should be a reasonable string length
                test_len = struct.unpack('<i', decrypted[:4])[0]
                if 0 < test_len < 10000:
                    return decrypted
        except Exception as e:
            print(f"  RSA decrypt failed: {e}")
        
        # Fallback: Simple1 (XOR 121)
        try:
            decrypted = PakCrypto._decrypt_simple1(ciphertext)
            test_len = struct.unpack('<i', decrypted[:4])[0]
            if 0 < test_len < 10000:
                print(f"  Using Simple1 fallback for index decryption")
                return decrypted
        except Exception as e:
            print(f"  Simple1 failed: {e}")
        
        print(f"  WARNING: Could not decrypt index properly")
        return ciphertext

# === Main Parser ===
def parse_pak(file_path: str, skip_verify=True):
    """Parse a Tencent PAK file and return its info and entries."""
    with open(file_path, 'rb') as f:
        content = memoryview(f.read())

    keystream = PakCrypto.zuc_keystream()
    info = TencentPakInfo(content, keystream)

    print(f"  File size: {len(content):,} bytes")
    print(f"  Magic: 0x{info.magic:08x}")
    print(f"  Version: {info.version}")
    print(f"  Index encrypted: {info.index_encrypted}")
    print(f"  Index size: {info.index_size:,} bytes")
    print(f"  Index offset: {info.index_offset:,}")

    # Parse index
    index_data = bytes(content[info.index_offset:][:info.index_size])
    if info.index_encrypted:
        try:
            index_data = PakCrypto.decrypt_index(index_data, info)
        except Exception as e:
            print(f"  WARNING: Failed to decrypt index: {e}")

    reader = Reader(index_data)
    mount_point = reader.string()
    num_entries = reader.u4()

    print(f"  Mount point: {mount_point}")
    print(f"  Number of entries: {num_entries}")

    entries = {}
    all_files = []
    for i in range(num_entries):
        file_path_str = reader.string()
        entry = TencentPakEntry(reader, info.version)
        entries[file_path_str] = entry
        all_files.append(file_path_str)

    print(f"  Total files parsed: {len(entries)}")
    return {
        'info': info,
        'mount_point': mount_point,
        'entries': entries,
        'all_files': all_files,
        'content': content,
    }


if __name__ == '__main__':
    file1 = '/home/z/my-project/upload/game_patch_4.5.0.21370.pak'
    file2 = '/home/z/my-project/upload/game_patch_4.5.0.21370 (1).pak'

    print("=" * 70)
    print("File 1: game_patch_4.5.0.21370.pak (no parenthesis)")
    print("=" * 70)
    r1 = parse_pak(file1)
    print()

    print("=" * 70)
    print("File 2: game_patch_4.5.0.21370 (1).pak (with parenthesis)")
    print("=" * 70)
    r2 = parse_pak(file2)
    print()

    # === COMPARISON ===
    print("=" * 70)
    print("COMPARISON RESULTS")
    print("=" * 70)

    paths1 = set(r1['entries'].keys())
    paths2 = set(r2['entries'].keys())

    only_in_1 = sorted(paths1 - paths2)
    only_in_2 = sorted(paths2 - paths1)
    common = sorted(paths1 & paths2)

    print(f"\n--- Files ONLY in File 1 (no paren): {len(only_in_1)} ---")
    for f in only_in_1:
        print(f"  {f}")

    print(f"\n--- Files ONLY in File 2 (with paren): {len(only_in_2)} ---")
    for f in only_in_2:
        print(f"  {f}")

    print(f"\n--- Common files: {len(common)} ---")

    modified = []
    size_differs = []
    for f in common:
        e1 = r1['entries'][f]
        e2 = r2['entries'][f]
        if e1.content_hash != e2.content_hash:
            modified.append(f)
        if e1.uncompressed_size != e2.uncompressed_size:
            size_differs.append(f)

    print(f"\n--- MODIFIED files (different content hash): {len(modified)} ---")
    for f in modified:
        e1 = r1['entries'][f]
        e2 = r2['entries'][f]
        print(f"  {f}")
        print(f"    File 1: hash={e1.content_hash.hex()[:20]}... usize={e1.uncompressed_size:>12,}  offset={e1.offset:>12,}  enc={e1.encrypted}  em={e1.encryption_method}  cm={e1.compression_method}")
        print(f"    File 2: hash={e2.content_hash.hex()[:20]}... usize={e2.uncompressed_size:>12,}  offset={e2.offset:>12,}  enc={e2.encrypted}  em={e2.encryption_method}  cm={e2.compression_method}")

    if size_differs:
        print(f"\n--- Files with different uncompressed sizes: {len(size_differs)} ---")
        for f in size_differs:
            e1 = r1['entries'][f]
            e2 = r2['entries'][f]
            print(f"  {f}: File1={e1.uncompressed_size:,} vs File2={e2.uncompressed_size:,}")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"File 1 (no paren) : {len(content):,} bytes, {len(r1['entries'])} entries, {len(only_in_1)} unique, {len(modified)} modified")
    print(f"File 2 (with paren): {len(content):,} bytes, {len(r2['entries'])} entries, {len(only_in_2)} unique")
    print(f"\nModified files total: {len(modified)}")
    if modified:
        print("\nModified file list:")
        for f in modified:
            print(f"  - {f}")
