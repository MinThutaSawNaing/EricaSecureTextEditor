"""Parity tests against Python itself; requires the rebuilt Windows DLL."""

import ctypes
import random
import sys
import unittest

import erica_storage


class NativeWordCountTests(unittest.TestCase):
    def assert_count(self, text):
        self.assertEqual(erica_storage.count_words(text), len(text.split()), repr(text))

    def test_all_unicode_codepoints_as_separators(self):
        # Batched comparison covers every code point (including lone surrogates)
        # without a million FFI calls. Spaces isolate each candidate's result.
        for start in range(0, sys.maxunicode + 1, 4096):
            text = " ".join("a" + chr(cp) + "b" for cp in
                            range(start, min(start + 4096, sys.maxunicode + 1)))
            self.assert_count(text)

    def test_every_python_whitespace_in_every_position(self):
        whitespace = [chr(cp) for cp in range(sys.maxunicode + 1) if chr(cp).isspace()]
        self.assertEqual(len(whitespace), 29)
        for space in whitespace:
            for text in [space, space * 3, space + "word", "word" + space,
                         "one" + space * 2 + "two", space + "one" + space + "two" + space]:
                with self.subTest(text=repr(text)):
                    self.assert_count(text)
        self.assert_count("".join(whitespace))

    def test_unicode_nul_and_surrogates(self):
        for text in ["", "one", "  one two\nthree  ", "မြန်မာ 日本語 😀 🔒",
                     "a\0b", "\ud800", "\udfff", "\ud800\udc00",
                     "😀\ud800\x1c\udfff\u00a0𐀀", "a\u200bb\ufeffc\u180ed",
                     "x " * 100000]:
            with self.subTest(length=len(text)):
                self.assert_count(text)

    def test_deterministic_mixed_text(self):
        rng = random.Random(42)
        alphabet = "ab😀မြန်မာ\0\ud800\udfff\u200b\ufeff" + "".join(
            chr(cp) for cp in range(0x3001) if chr(cp).isspace())
        for _ in range(200):
            self.assert_count("".join(rng.choices(alphabet, k=rng.randrange(1000))))

    def test_type_rejection(self):
        for value in [None, b"words", 123, ["words"]]:
            with self.subTest(value=value), self.assertRaises(TypeError):
                erica_storage.count_words(value)

    def test_abi_and_invalid_arguments(self):
        self.assertEqual(erica_storage.backend_version(), 1)
        counter = erica_storage._native().erica_count_words_utf16
        self.assertEqual(counter(None, 0), 0)
        self.assertEqual(counter(None, 1), 0)
        units = (ctypes.c_uint16 * 1)(ord("a"))
        self.assertEqual(counter(units, ctypes.c_size_t(-1).value), 0)
        misaligned = ctypes.cast(ctypes.addressof(units) + 1, ctypes.POINTER(ctypes.c_uint16))
        self.assertEqual(counter(misaligned, 1), 0)


if __name__ == "__main__":
    unittest.main()