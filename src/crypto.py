"""
Crypto - AES-256-GCM encryption for session bundles

Uses a passphrase-derived key (PBKDF2-HMAC-SHA256) so users don't need to
manage raw key files — they only need to remember a passphrase.

Key derivation:
  - Algorithm: PBKDF2-HMAC-SHA256
  - Iterations: 600,000 (OWASP 2024 recommendation)
  - Key length: 256-bit (32 bytes)
  - Salt: random per bundle (embedded in the encrypted output)

Encryption:
  - Algorithm: AES-256-GCM (authenticated encryption)
  - IV/Nonce: 96-bit (12 bytes), random per encryption
  - Auth tag: 128-bit (16 bytes)

Bundle format (encrypted):
  Salt (16 bytes) || IV (12 bytes) || AuthTag (16 bytes) || Ciphertext

The bundle salt is random and unique per encryption. Because the key is always
derived from (passphrase + bundle_salt), the same passphrase works on any
machine — no machine-specific state is needed for decryption.

Stored passphrase format (crypto-setup):
  The passphrase is XOR-obfuscated with a machine-specific pad so it is not
  stored in plain text. The obfuscation pad is derived via PBKDF2 from a
  machine-specific salt. This is NOT cryptographic protection of the passphrase
  — it only prevents casual inspection. Anyone with access to both files can
  recover the passphrase.
"""

import os
import stat
from pathlib import Path
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    raise ImportError(
        "The 'cryptography' package is required for encryption.\n"
        "Install it with: pip install cryptography"
    )

KEY_DIR = Path.home() / ".claude-context-sync"
PASSPHRASE_FILE = KEY_DIR / "passphrase"
MACHINE_SALT_FILE = KEY_DIR / "salt"

PBKDF2_ITERATIONS = 600_000
KEY_LENGTH = 32  # 256-bit
SALT_LENGTH = 16
IV_LENGTH = 12


class PassphraseNotFound(Exception):
    """Raised when the saved passphrase file does not exist."""
    pass


# Keep old name as alias so existing call-sites don't break
EncryptionKeyNotFound = PassphraseNotFound


def _get_or_create_machine_salt() -> bytes:
    """Return the machine-specific salt, creating it if it doesn't exist."""
    KEY_DIR.mkdir(parents=True, exist_ok=True)

    if MACHINE_SALT_FILE.exists():
        return MACHINE_SALT_FILE.read_bytes()

    salt = os.urandom(SALT_LENGTH)
    MACHINE_SALT_FILE.write_bytes(salt)
    _set_permissions_600(MACHINE_SALT_FILE)
    return salt


def _machine_obfuscation_pad(length: int) -> bytes:
    """
    Derive a deterministic pad from the machine salt.
    Used to XOR-obfuscate the stored passphrase (not cryptographic security).
    """
    machine_salt = _get_or_create_machine_salt()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=machine_salt,
        iterations=1,  # Just a pad, not a security KDF
    )
    return kdf.derive(b"claude-context-sync-pad")


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a passphrase + salt using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _set_permissions_600(path: Path) -> None:
    """Set file permissions to owner read/write only (0600)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass  # Windows doesn't support POSIX chmod — silently skip


def setup_key(passphrase: str) -> str:
    """
    Save the passphrase locally (XOR-obfuscated with a machine-specific pad).

    The passphrase — not a derived key — is stored, so the same passphrase
    can correctly decrypt bundles created on any machine. Run this command
    with the same passphrase on every device.

    Args:
        passphrase: User-provided passphrase (min 8 characters recommended)

    Returns:
        Path to the saved passphrase file as a string
    """
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    raw = passphrase.encode("utf-8")
    pad = _machine_obfuscation_pad(len(raw))
    obfuscated = bytes(a ^ b for a, b in zip(raw, pad))
    # Prefix with the length so we know how many bytes to read back
    PASSPHRASE_FILE.write_bytes(len(raw).to_bytes(2, "big") + obfuscated)
    _set_permissions_600(PASSPHRASE_FILE)
    return str(PASSPHRASE_FILE)


def load_passphrase() -> str:
    """
    Load the saved passphrase from ~/.claude-context-sync/passphrase.

    Returns:
        The plaintext passphrase string

    Raises:
        PassphraseNotFound: If the passphrase file does not exist
    """
    if not PASSPHRASE_FILE.exists():
        raise PassphraseNotFound(
            f"No saved passphrase found at {PASSPHRASE_FILE}.\n"
            "Run 'claude-sync crypto-setup' to configure one."
        )
    data = PASSPHRASE_FILE.read_bytes()
    length = int.from_bytes(data[:2], "big")
    obfuscated = data[2:2 + length]
    pad = _machine_obfuscation_pad(length)
    return bytes(a ^ b for a, b in zip(obfuscated, pad)).decode("utf-8")


def load_key() -> bytes:
    """
    Compatibility shim: kept so call-sites that imported load_key() still work.
    Raises PassphraseNotFound (same base class as EncryptionKeyNotFound).

    Use load_passphrase() in new code.
    """
    raise PassphraseNotFound(
        "load_key() is no longer used. Use load_passphrase() instead."
    )


def encrypt_bundle(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt bundle data with AES-256-GCM.

    A fresh random salt is generated for each encryption and embedded in the
    output. The key is derived from (passphrase + bundle_salt), so the same
    passphrase on any machine can decrypt the bundle.

    Bundle format:
        Salt (16 bytes) || IV (12 bytes) || AuthTag (16 bytes) || Ciphertext

    Args:
        data: Raw bundle bytes to encrypt
        passphrase: Plaintext passphrase

    Returns:
        Encrypted bundle bytes
    """
    salt = os.urandom(SALT_LENGTH)
    key = _derive_key(passphrase, salt)
    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(key)

    ct_with_tag = aesgcm.encrypt(iv, data, None)
    auth_tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]

    return salt + iv + auth_tag + ciphertext


def decrypt_bundle(data: bytes, passphrase: str) -> bytes:
    """
    Decrypt an AES-256-GCM encrypted bundle.

    The key is always derived from (passphrase + bundle_salt) where bundle_salt
    is read from the first 16 bytes of the encrypted data.

    Args:
        data: Encrypted bundle bytes (Salt || IV || AuthTag || Ciphertext)
        passphrase: Plaintext passphrase

    Returns:
        Decrypted bundle bytes

    Raises:
        ValueError: If the data is too short or authentication tag is invalid
    """
    min_length = SALT_LENGTH + IV_LENGTH + 16  # salt + iv + auth_tag
    if len(data) < min_length:
        raise ValueError("Encrypted data is too short — may be corrupted")

    salt = data[:SALT_LENGTH]
    iv = data[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    auth_tag = data[SALT_LENGTH + IV_LENGTH:SALT_LENGTH + IV_LENGTH + 16]
    ciphertext = data[SALT_LENGTH + IV_LENGTH + 16:]

    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)

    try:
        return aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    except Exception:
        raise ValueError(
            "Decryption failed — wrong passphrase or corrupted bundle."
        )
