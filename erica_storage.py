"""Small, typed interface to the required Windows Rust storage library.

Storage payloads and UTF-16 word-count buffers cross this seam. Encryption and
password handling stay with cryptography. No Python write fallback silently
bypasses native guarantees.
"""

import ctypes
import os
from pathlib import Path
import sys


_library = None


def _native():
    global _library
    if _library is None:
        if sys.platform != "win32":
            raise OSError("The Erica Rust storage module requires Windows.")
        directory = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        path = directory / "erica_storage.dll"
        try:
            library = ctypes.CDLL(str(path))
        except OSError as exc:
            raise OSError(f"Cannot load Rust storage module at {path}. Run build_native.ps1 first.") from exc
        library.erica_storage_abi_version.argtypes = []
        library.erica_storage_abi_version.restype = ctypes.c_uint32
        library.erica_validate_encrypted.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.erica_validate_encrypted.restype = ctypes.c_int32
        library.erica_atomic_write.argtypes = [ctypes.POINTER(ctypes.c_uint16), ctypes.c_size_t,
                                              ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int32]
        library.erica_atomic_write.restype = ctypes.c_uint32
        if library.erica_storage_abi_version() != 1:
            raise OSError("Incompatible Rust storage module; rebuild with build_native.ps1.")
        try:
            counter = library.erica_count_words_utf16
        except AttributeError as exc:
            raise OSError("Rust storage module lacks word counting; rebuild with build_native.ps1.") from exc
        counter.argtypes = [ctypes.POINTER(ctypes.c_uint16), ctypes.c_size_t]
        counter.restype = ctypes.c_size_t
        _library = library
    return _library


def backend_version():
    return _native().erica_storage_abi_version()


def count_words(text):
    """Return len(text.split()) using native UTF-16 scanning without word lists.

    Accepts str, including embedded NUL and lone surrogates. A copied buffer
    remains live throughout the call; no CPython string-layout assumptions.
    """
    if not isinstance(text, str):
        raise TypeError("Word-count text must be str.")
    encoded = text.encode("utf-16-le", errors="surrogatepass")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    return _native().erica_count_words_utf16(units, len(units))


def _require_bytes(data):
    if not isinstance(data, bytes):
        raise TypeError("Storage payload must be bytes.")


def validate_encrypted(data):
    """Check legacy envelope structure, not password validity or authenticity."""
    _require_bytes(data)
    if _native().erica_validate_encrypted(data, len(data)) != 0:
        raise ValueError("Invalid encrypted file layout (minimum 80 bytes and aligned ciphertext required).")


def atomic_write(path, data, *, read_only=False, encrypted=False):
    """Replace a file using a synchronized same-directory native temporary file.

    Parent directory must already exist and be trusted. Failure before replacement
    leaves original bytes intact. Existing DACL policy/protection is copied to
    the empty temp before writing. Other metadata (owner, audit policy, streams)
    is not preserved. This does not authenticate bytes or guarantee power-loss recovery.
    """
    _require_bytes(data)
    path = os.fsdecode(os.fspath(path))
    if not path or "\0" in path:
        raise ValueError("A nonempty path without NUL characters is required.")
    absolute = os.path.abspath(path)
    encoded = absolute.encode("utf-16-le")
    units = (ctypes.c_uint16 * (len(encoded) // 2)).from_buffer_copy(encoded)
    if encrypted:
        validate_encrypted(data)
    code = _native().erica_atomic_write(units, len(units), data, len(data), int(bool(read_only)))
    if code:
        error = ctypes.WinError(code)
        error.filename = absolute
        raise error