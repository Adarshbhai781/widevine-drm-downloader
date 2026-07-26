"""Bypass the RSA index_hash assertion and just check SHA1 directly.

For game_patch_4.5.0.21370.pak, the RSA-extracted hash from packed_index_hash
does not match the index_hash field. We will:
1. Disable the RSA assertion
2. Compute SHA1 of the index_data
3. See if it matches index_hash
4. If yes, the index is fine - we can unpack
5. If no, the index_hash field itself may need different decryption
"""
import sys, struct, zlib, hashlib
sys.path.insert(0, '/home/z/my-project/pak_workspace')
import importlib.util
spec = importlib.util.spec_from_file_location('dhvip', '/home/z/my-project/pak_workspace/DHVIP.py')
dhvip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dhvip)

from pathlib import Path
from Crypto.Hash import SHA1

pak_file = Path('/home/z/my-project/pak_workspace/PAK/game_patch_4.5.0.21370.pak')
with open(pak_file, 'rb') as f:
    data = f.read()

keystream = dhvip.PakCrypto.zuc_keystream()
info = dhvip.TencentPakInfo(data, keystream)

print(f'pak_info.version = {info.version}')
print(f'pak_info.index_offset = {info.index_offset}')
print(f'pak_info.index_size = {info.index_size}')
print(f'pak_info.index_encrypted = {info.index_encrypted}')

# Get index data
index_data = data[info.index_offset:][:info.index_size]
print(f'index_data length = {len(index_data)}')

if info.index_encrypted:
    decrypted_index = dhvip.PakCrypto.decrypt_index(index_data, info)
    print(f'decrypted index length = {len(decrypted_index)}')
    sha1_decrypted = SHA1.new(decrypted_index).digest()
    print(f'SHA1(decrypted index) = {sha1_decrypted.hex()}')
    print(f'pak_info.index_hash   = {info.index_hash.hex()}')
    print(f'Match (decrypted)?    = {sha1_decrypted == info.index_hash}')

    # Also try SHA1 of the raw (still encrypted) index data
    sha1_raw = SHA1.new(index_data).digest()
    print(f'SHA1(raw index_data)  = {sha1_raw.hex()}')
    print(f'Match (raw)?          = {sha1_raw == info.index_hash}')

    # Try rsa_extract output
    rsa_hash = dhvip.PakCrypto.rsa_extract(info.packed_index_hash, dhvip.RSA_MOD_2)
    print(f'RSA(packed_index_hash)= {rsa_hash.hex()}')

    # Try RSA_MOD_1
    try:
        rsa_hash_1 = dhvip.PakCrypto.rsa_extract(info.packed_index_hash, dhvip.RSA_MOD_1)
        print(f'RSA_MOD_1(packed)     = {rsa_hash_1.hex()}')
        print(f'Match RSA_MOD_1?      = {rsa_hash_1 == info.index_hash}')
    except Exception as e:
        print(f'RSA_MOD_1 error: {e}')
else:
    sha1_raw = SHA1.new(index_data).digest()
    print(f'SHA1(index_data) = {sha1_raw.hex()}')
    print(f'index_hash       = {info.index_hash.hex()}')
    print(f'Match? = {sha1_raw == info.index_hash}')
