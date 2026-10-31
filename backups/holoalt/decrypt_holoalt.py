"""Decrypt the AES-256-GCM holoalt backup. Requires: pip install cryptography"""
from pathlib import Path
import getpass
import hashlib
import os
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.exceptions import InvalidTag

MAGIC = b"HDENC001"
EXPECTED_SHA256 = "14f71c96c619258795fa7ec01dcd38145e59ac2dc29bbcbb72b584ed154b63d4"

def decrypt_archive(src: Path, dst: Path | None, key_hex: str):
    key = bytes.fromhex(key_hex.strip())
    if len(key) != 32:
        raise ValueError("The key must contain 64 hexadecimal characters (32 bytes).")
    total = src.stat().st_size
    if total <= 36:
        raise ValueError("The encrypted file is too short.")
    with src.open("rb") as fin:
        if fin.read(8) != MAGIC:
            raise ValueError("Not a holoalt encrypted archive.")
        nonce = fin.read(12)
        fin.seek(total - 16)
        tag = fin.read(16)
        fin.seek(20)
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        checksum = hashlib.sha256()
        remaining = total - 36
        partial = dst.with_suffix(dst.suffix + ".partial") if dst else None
        try:
            with (partial.open("xb") if partial else open(os.devnull, "wb")) as fout:
                while remaining > 0:
                    block = fin.read(min(4 * 1024 * 1024, remaining))
                    if not block:
                        raise ValueError("Encrypted file truncated.")
                    remaining -= len(block)
                    plain = cipher.update(block)
                    checksum.update(plain)
                    fout.write(plain)
                tail = cipher.finalize()
                checksum.update(tail)
                fout.write(tail)
            if checksum.hexdigest() != EXPECTED_SHA256:
                raise ValueError("The decrypted ZIP checksum is incorrect.")
            if dst:
                os.replace(partial, dst)
        except Exception:
            if partial and partial.exists():
                partial.unlink()
            raise
    return checksum.hexdigest()

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python decrypt_holoalt.py INPUT.zip.aesgcm [OUTPUT.zip]")
        print("If OUTPUT.zip is omitted, this verifies without writing a ZIP.")
        sys.exit(2)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) == 3 else None
    if dst and dst.exists():
        raise SystemExit("Output already exists; refusing to overwrite it.")
    key = getpass.getpass("Paste the private restore key (64 hex chars): ")
    try:
        checksum = decrypt_archive(src, dst, key)
    except (InvalidTag, ValueError) as e:
        raise SystemExit(f"Decryption or integrity verification failed: {e}")
    print("Verified SHA256:", checksum)
    if dst:
        print("Restored ZIP:", dst.resolve())
