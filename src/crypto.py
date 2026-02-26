"""
Crypto - AES-256-GCM encryption for session bundles

Uses a passphrase-derived key (PBKDF2-HMAC-SHA256) so users don't need to
manage raw key files — they only need to remember a passphrase.

Key derivation:
  - Algorithm: PBKDF2-HMAC-SHA256
  - Iterations: 600,000 (OWASP 2024 recommendation)
  - Key length: 256-bit (32 bytes)

Encryption:
  - Algorithm: AES-256-GCM (authenticated encryption)
  - IV/Nonce: 96-bit (12 bytes), random per encryption
  - Auth tag: 128-bit (16 bytes)

Bundle format (encrypted):
  Salt (16 bytes) || IV (12 bytes) || AuthTag (16 bytes) || Ciphertext

Stored key format (crypto-setup):
  A fixed salt per machine is used so the same passphrase always produces
  the same key on the same machine. Key is stored as raw bytes in
  ~/.claude-context-sync/key with mode 0600.
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
KEY_FILE = KEY_DIR / "key"
MACHINE_SALT_FILE = KEY_DIR / "salt"

PBKDF2_ITERATIONS = 600_000
KEY_LENGTH = 32  # 256-bit
SALT_LENGTH = 16
IV_LENGTH = 12


class EncryptionKeyNotFound(Exception):
    """Raised when the local key file does not exist."""
    pass


def _get_or_create_machine_salt() -> bytes:
    """
    Return the machine-specific salt, creating it if it doesn't exist.

    Using a fixed salt per machine means the same passphrase always
    produces the same key on the same machine, enabling automatic
    hook-based encryption without prompts.
    """
    KEY_DIR.mkdir(parents=True, exist_ok=True)

    if MACHINE_SALT_FILE.exists():
        return MACHINE_SALT_FILE.read_bytes()

    salt = os.urandom(SALT_LENGTH)
    MACHINE_SALT_FILE.write_bytes(salt)
    _set_permissions_600(MACHINE_SALT_FILE)
    return salt


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a passphrase using PBKDF2-HMAC-SHA256."""
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
    Derive and save the encryption key from a passphrase.

    Uses the machine-specific salt so the same passphrase on the same
    machine always produces the same key. Run this on every machine with
    the same passphrase to enable cross-machine decryption.

    Args:
        passphrase: User-provided passphrase (min 8 characters recommended)

    Returns:
        Path to the saved key file as a string
    """
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    salt = _get_or_create_machine_salt()
    key = _derive_key(passphrase, salt)
    KEY_FILE.write_bytes(key)
    _set_permissions_600(KEY_FILE)
    return str(KEY_FILE)


def load_key() -> bytes:
    """
    Load the saved key from ~/.claude-context-sync/key.

    Returns:
        Raw 32-byte AES key

    Raises:
        EncryptionKeyNotFound: If the key file does not exist
    """
    if not KEY_FILE.exists():
        raise EncryptionKeyNotFound(
            f"No encryption key found at {KEY_FILE}.\n"
            "Run 'claude-sync crypto-setup' to configure one."
        )
    return KEY_FILE.read_bytes()


def encrypt_bundle(data: bytes, key: Optional[bytes] = None, passphrase: Optional[str] = None) -> bytes:
    """
    Encrypt bundle data with AES-256-GCM.

    Exactly one of `key` or `passphrase` must be provided.

    Bundle format:
        Salt (16 bytes) || IV (12 bytes) || AuthTag (16 bytes) || Ciphertext

    Args:
        data: Raw bundle bytes to encrypt
        key: 32-byte AES key (from load_key())
        passphrase: Passphrase to derive key from (for manual one-time use)

    Returns:
        Encrypted bundle bytes
    """
    if key is None and passphrase is None:
        raise ValueError("Either 'key' or 'passphrase' must be provided")

    # Generate a fresh random salt for this encryption (included in output)
    salt = os.urandom(SALT_LENGTH)

    if key is None:
        key = _derive_key(passphrase, salt)

    iv = os.urandom(IV_LENGTH)
    aesgcm = AESGCM(key)

    # AESGCM.encrypt returns ciphertext + auth_tag concatenated
    ct_with_tag = aesgcm.encrypt(iv, data, None)
    # GCM auth tag is always the last 16 bytes
    auth_tag = ct_with_tag[-16:]
    ciphertext = ct_with_tag[:-16]

    return salt + iv + auth_tag + ciphertext


def decrypt_bundle(data: bytes, key: Optional[bytes] = None, passphrase: Optional[str] = None) -> bytes:
    """
    Decrypt an AES-256-GCM encrypted bundle.

    Exactly one of `key` or `passphrase` must be provided.

    Args:
        data: Encrypted bundle bytes (Salt || IV || AuthTag || Ciphertext)
        key: 32-byte AES key (from load_key())
        passphrase: Passphrase to derive key from

    Returns:
        Decrypted bundle bytes

    Raises:
        ValueError: If the data is too short or the tag is invalid (wrong key/passphrase)
    """
    if key is None and passphrase is None:
        raise ValueError("Either 'key' or 'passphrase' must be provided")

    min_length = SALT_LENGTH + IV_LENGTH + 16  # salt + iv + auth_tag
    if len(data) < min_length:
        raise ValueError("Encrypted data is too short — may be corrupted")

    salt = data[:SALT_LENGTH]
    iv = data[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    auth_tag = data[SALT_LENGTH + IV_LENGTH:SALT_LENGTH + IV_LENGTH + 16]
    ciphertext = data[SALT_LENGTH + IV_LENGTH + 16:]

    if key is None:
        key = _derive_key(passphrase, salt)

    aesgcm = AESGCM(key)

    try:
        # AESGCM.decrypt expects ciphertext + auth_tag concatenated
        return aesgcm.decrypt(iv, ciphertext + auth_tag, None)
    except Exception:
        raise ValueError(
            "Decryption failed — wrong passphrase or corrupted bundle."
        )
