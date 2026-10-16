import ctypes
import os
import stat
from pathlib import Path
import tempfile
import unittest

import erica_storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        for path in self.root.iterdir():
            if path.is_file():
                path.chmod(0o600)
        self.temp.cleanup()

    def test_native_backend_is_loaded(self):
        self.assertEqual(erica_storage.backend_version(), 1)

    def test_unicode_path_create_and_replace_read_only(self):
        path = self.root / "notes-မြန်မာ-🔒.erica"
        erica_storage.atomic_write(path, b"old", read_only=True)
        self.assertTrue(path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
        erica_storage.atomic_write(path, b"complete replacement", read_only=True)
        self.assertEqual(path.read_bytes(), b"complete replacement")
        self.assertTrue(path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_empty_bytes_are_supported_for_raw_files(self):
        path = self.root / "empty"
        erica_storage.atomic_write(path, b"")
        self.assertEqual(path.read_bytes(), b"")

    def test_legacy_envelope_layout_validation(self):
        for size in [80, 96, 112, 1024]:
            erica_storage.validate_encrypted(b"x" * size)
        for size in [0, 16, 48, 64, 79, 81, 95]:
            with self.subTest(size=size), self.assertRaises(ValueError):
                erica_storage.validate_encrypted(b"x" * size)

    def test_invalid_encrypted_write_keeps_existing_file(self):
        path = self.root / "existing.erica"
        path.write_bytes(b"previous document")
        with self.assertRaises(ValueError):
            erica_storage.atomic_write(path, b"invalid", encrypted=True)
        self.assertEqual(path.read_bytes(), b"previous document")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_missing_parent_does_not_create_directories(self):
        with self.assertRaises(OSError):
            erica_storage.atomic_write(self.root / "missing" / "file", b"data")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_directory_target_is_not_replaced(self):
        path = self.root / "folder"
        path.mkdir()
        with self.assertRaises(OSError):
            erica_storage.atomic_write(path, b"data")
        self.assertTrue(path.is_dir())
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_invalid_inputs_are_rejected_before_ffi(self):
        with self.assertRaises(ValueError):
            erica_storage.atomic_write("bad\0path", b"data")
        with self.assertRaises(TypeError):
            erica_storage.atomic_write(self.root / "file", "not bytes")

    @unittest.skipUnless(os.name == "nt", "Windows sharing semantics")
    def test_blocked_replace_preserves_existing_file_and_cleans_temp(self):
        path = self.root / "locked.erica"
        path.write_bytes(b"old complete data")
        path.chmod(0o444)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                           ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        create.restype = ctypes.c_void_p
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        # Allow reading/writing but not FILE_SHARE_DELETE: replacement must fail.
        handle = create(str(path), 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(OSError):
                erica_storage.atomic_write(path, b"new data", read_only=True)
            self.assertEqual(path.read_bytes(), b"old complete data")
            self.assertTrue(path.stat().st_file_attributes & stat.FILE_ATTRIBUTE_READONLY)
            self.assertEqual(list(self.root.iterdir()), [path])
        finally:
            close(handle)


if __name__ == "__main__":
    unittest.main()