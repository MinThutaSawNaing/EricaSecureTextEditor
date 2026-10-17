"""Thin ctypes adapter to Erica's required Rust organization backend.

Token rules, random generation, checks, scrypt/AES-GCM, envelope parsing, DPAPI,
base64, destination protection and organization file I/O are implemented in Rust.
There is deliberately no Python crypto or local-storage fallback. Python only
marshals the C ABI and translates errors for the existing Qt application.

The version-1 file and DPAPI payload formats remain compatible. Tokens crossing
the UI/FFI boundary are Python strings and cannot be reliably erased by Python;
callers must not log them and should limit their lifetime.
"""

import ctypes
import os

import erica_storage


class InvalidOrganizationFile(ValueError):
    """Not a supported, structurally valid organization-encrypted file."""


class OrganizationIntegrityError(ValueError):
    """Authentication failed: wrong tokens or damaged/modified data."""


_bound_library = None


def _native():
    global _bound_library
    library = erica_storage._native()
    if library is not _bound_library:
        try:
            version = library.erica_organization_abi_version
            version.argtypes = []
            version.restype = ctypes.c_uint32
            call = library.erica_org_call
            call.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_size_t,
                             ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_size_t)]
            call.restype = ctypes.c_uint32
            release = library.erica_org_free
            release.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            release.restype = None
        except AttributeError as exc:
            raise OSError("Rust organization backend missing; rebuild with build_native.ps1.") from exc
        if version() != 2:
            raise OSError("Incompatible Rust organization backend; rebuild with build_native.ps1.")
        _bound_library = library
    return library


def _call(operation, payload=b""):
    library = _native()
    output = ctypes.c_void_p()
    length = ctypes.c_size_t()
    code = library.erica_org_call(operation, payload, len(payload),
                                  ctypes.byref(output), ctypes.byref(length))
    try:
        if code:
            errors = {
                1: (ValueError, "Each token requires exactly 16 ASCII decimal digits (0-9), and the two tokens must be distinct. Check values must match Erica's generated five-digit values."),
                2: (InvalidOrganizationFile, "Invalid or unsupported organization file."),
                3: (OrganizationIntegrityError, "Organization authentication failed: wrong tokens or damaged file."),
                4: (RuntimeError, "Windows DPAPI token protection failed."),
                5: (RuntimeError, "Rust organization backend operation failed."),
                6: (ValueError, "Protection modes differ. Save As to a new filename to convert this file."),
                7: (OSError, "Rust organization backend could not access the file."),
            }
            kind, message = errors.get(code, (RuntimeError, "Rust organization backend internal error."))
            raise kind(message)
        if length.value and not output.value:
            raise RuntimeError("Rust organization backend returned an invalid buffer.")
        return ctypes.string_at(output, length.value) if length.value else b""
    finally:
        if output.value:
            library.erica_org_free(output, length.value)


def _ascii(value, size=None):
    """Marshal fixed-width ASCII fields without coercion or truncation."""
    if not isinstance(value, str) or (size is not None and len(value) != size):
        raise ValueError("Invalid organization input field.")
    try:
        return value.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Organization input fields must use ASCII characters.") from None


def _pair(tokens):
    if not isinstance(tokens, tuple) or len(tokens) != 2:
        raise ValueError("Provide an ordered tuple containing two tokens.")
    try:
        return _ascii(tokens[0], 16) + _ascii(tokens[1], 16)
    except ValueError:
        raise ValueError("Each token requires exactly 16 ASCII decimal digits (0-9).") from None


def _tokens(data):
    text = data.decode("ascii")
    return text[:16], text[16:]


def _bytes(data):
    if not isinstance(data, bytes):
        raise TypeError("Organization payload must be bytes.")
    return data


def _path(path):
    return os.path.abspath(os.fsdecode(os.fspath(path))).encode("utf-8")


def validate_tokens(token1, token2):
    return _tokens(_call(1, _pair((token1, token2))))


def check_value(token):
    """Ask Rust for Erica's deterministic, zero-padded five-decimal-digit check."""
    return _call(2, _ascii(token, 16)).decode("ascii")


def validate_check_values(token1, check1, token2, check2):
    return _tokens(_call(3, _pair((token1, token2)) + _ascii(check1, 5) + _ascii(check2, 5)))


def generate_tokens():
    return _tokens(_call(4))


def is_organization_data(data):
    return isinstance(data, bytes) and _call(5, data) == b"\x01"


def encrypt_bytes(data, tokens):
    if not isinstance(data, bytes):
        raise ValueError("Organization payload must be bytes.")
    return _call(6, _pair(tokens) + _bytes(data))


def decrypt_bytes(data, tokens):
    if not isinstance(data, bytes):
        raise InvalidOrganizationFile("Organization payload must be bytes.")
    return _call(7, _pair(tokens) + _bytes(data))


def protect_tokens(tokens):
    return _call(8, _pair(tokens)).decode("ascii")


def unprotect_tokens(protected):
    return _tokens(_call(9, _ascii(protected)))


def verify_destination(path, credential):
    """Rust owns cross-mode and wrong-organization overwrite protection."""
    prefix = b"\x01" + _pair(credential) if isinstance(credential, tuple) else b"\x00"
    _call(10, prefix + _path(path))


def file_uses_organization(path):
    return _call(11, _path(path)) == b"\x01"


def write_file(path, data, tokens):
    """Guard, encrypt and atomically write an organization file entirely in Rust."""
    encoded = _path(path)
    _call(12, _pair(tokens) + len(encoded).to_bytes(4, "little") + encoded + _bytes(data))


def read_file(path, tokens):
    return _call(13, _pair(tokens) + _path(path))