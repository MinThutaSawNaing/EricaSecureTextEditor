import os
import tempfile
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QPoint

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import erica_secure_text_editor as appmod


class EricaAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = appmod.QApplication.instance() or appmod.QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        appmod.CONFIG_PATH = self.temp_dir.name
        appmod.CONFIG_FILE = os.path.join(self.temp_dir.name, "config.json")
        appmod.RECOVERY_FILE = os.path.join(self.temp_dir.name, "recovery.enc")
        appmod._TEST_RECOVERY_KEY_PROTECTOR = lambda secret: f"protected::{secret}"
        appmod._TEST_RECOVERY_KEY_UNPROTECTOR = lambda secret: secret.split("protected::", 1)[1]
        self.hardened_paths = []
        appmod._TEST_HARDEN_PRIVATE_FILE_HOOK = self.hardened_paths.append
        self.window = appmod.MainWindow()

    def tearDown(self):
        self.window.close()
        appmod._TEST_RECOVERY_KEY_PROTECTOR = None
        appmod._TEST_RECOVERY_KEY_UNPROTECTOR = None
        appmod._TEST_HARDEN_PRIVATE_FILE_HOOK = None
        self.temp_dir.cleanup()

    def test_encrypt_roundtrip(self):
        encrypted = appmod.encrypt_text("hello", "Passw0rd!")
        self.assertEqual(appmod.decrypt_text(encrypted, "Passw0rd!"), "hello")

    def test_recent_files_and_last_session(self):
        test_file = os.path.join(self.temp_dir.name, "sample.erica")
        with open(test_file, "wb") as handle:
            handle.write(b"data")

        appmod.save_recent_file(test_file)
        appmod.save_last_session_files([test_file])

        self.assertEqual(appmod.get_recent_files(), [test_file])
        self.assertEqual(appmod.get_last_session_files(), [test_file])

    def test_recovery_snapshot_roundtrip(self):
        self.window.current_editor.setPlainText("recover me")
        self.window.current_editor.document().setModified(True)
        self.window.autosave_recovery_snapshot()

        self.assertTrue(os.path.exists(appmod.RECOVERY_FILE))

        with open(appmod.RECOVERY_FILE, "rb") as handle:
            recovered = appmod.decrypt_bytes(handle.read(), appmod.get_recovery_key())
        self.assertIn("recover me", recovered.decode("utf-8"))

        config = appmod.load_config()
        self.assertNotIn("recovery_key", config)
        self.assertTrue(config["recovery_key_protected"].startswith("protected::"))
        self.assertIn(appmod.RECOVERY_FILE, self.hardened_paths)

    def test_save_and_resave_same_file(self):
        fd, path = tempfile.mkstemp(dir=self.temp_dir.name, suffix=".erica")
        os.close(fd)
        os.unlink(path)

        with patch.object(appmod.QMessageBox, "question", return_value=appmod.QMessageBox.StandardButton.No), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(path, "Erica Secure Files (*.erica)")):
            self.window.prompt_password = lambda *args, **kwargs: "Passw0rd!"
            self.window.current_editor.setPlainText("first")
            self.window.save_as_file()
            self.window.current_editor.setPlainText("second")
            self.window.save_file()

        with open(path, "rb") as handle:
            decrypted = appmod.decrypt_text(handle.read(), "Passw0rd!")
        self.assertIn("second", decrypted)
        self.assertIsNone(self.window.get_current_password())

    def test_get_recovery_key_migrates_legacy_plaintext_key(self):
        appmod.save_config({"recovery_key": "legacy-secret"})

        recovered_key = appmod.get_recovery_key()

        self.assertEqual(recovered_key, "legacy-secret")
        config = appmod.load_config()
        self.assertNotIn("recovery_key", config)
        self.assertEqual(config["recovery_key_protected"], "protected::legacy-secret")
        self.assertIn(appmod.CONFIG_FILE, self.hardened_paths)

    def test_open_external_link_blocks_unsafe_scheme(self):
        with patch.object(appmod.QMessageBox, "warning") as warning_mock, \
             patch.object(appmod.QDesktopServices, "openUrl") as open_mock:
            self.window.openExternalLink("file:///C:/secret.txt")

        warning_mock.assert_called_once()
        open_mock.assert_not_called()

    def test_open_external_link_allows_https(self):
        with patch.object(appmod.QMessageBox, "warning") as warning_mock, \
             patch.object(appmod.QDesktopServices, "openUrl") as open_mock:
            self.window.openExternalLink("https://example.com")

        warning_mock.assert_not_called()
        open_mock.assert_called_once()

    def test_editor_anchor_blocks_unsafe_link(self):
        editor = appmod.ClickableTextBrowser()

        with patch.object(editor, "anchorAt", return_value="file:///C:/secret.txt"), \
             patch.object(appmod.QMessageBox, "warning") as warning_mock, \
             patch.object(appmod.QDesktopServices, "openUrl") as open_mock:
            class _Event:
                def button(self):
                    return appmod.Qt.MouseButton.LeftButton

                def pos(self):
                    return QPoint(0, 0)

            editor.mouseReleaseEvent(_Event())

        warning_mock.assert_called_once()
        open_mock.assert_not_called()

    def test_save_config_hardens_private_file(self):
        appmod.save_config({"theme": "dark"})
        self.assertIn(appmod.CONFIG_FILE, self.hardened_paths)

    def test_save_adds_erica_extension_when_missing(self):
        path = os.path.join(self.temp_dir.name, "notes")

        with patch.object(appmod.QMessageBox, "question", return_value=appmod.QMessageBox.StandardButton.No), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(path, "Erica Secure Files (*.erica)")):
            self.window.prompt_password = lambda *args, **kwargs: "Passw0rd!"
            self.window.current_editor.setPlainText("extension test")
            self.window.save_as_file()

        saved_path = f"{path}{appmod.DOCUMENT_EXTENSION}"
        self.assertTrue(os.path.exists(saved_path))

    def test_timeout_single_shutdown(self):
        calls = {"warning": 0, "quit": 0}
        self.window.remaining_time = 1

        with patch.object(appmod.QMessageBox, "warning", side_effect=lambda *args, **kwargs: calls.__setitem__("warning", calls["warning"] + 1) or appmod.QMessageBox.StandardButton.Ok), \
             patch.object(self.app, "quit", side_effect=lambda: calls.__setitem__("quit", calls["quit"] + 1)):
            self.window.handle_timeout_tick()
            self.window.handle_timeout_tick()

        self.assertEqual(calls["warning"], 1)
        self.assertEqual(calls["quit"], 1)

    def test_table_crud_and_merge_split(self):
        editor = self.window.current_editor
        cursor = editor.textCursor()
        table_format = appmod.QTextTableFormat()
        table_format.setBorder(1)
        table = cursor.insertTable(2, 2, table_format)

        editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.window.insert_table_row_below()
        editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.window.insert_table_column_right()
        self.assertEqual((table.rows(), table.columns()), (3, 3))

        start = table.cellAt(0, 0).firstCursorPosition()
        end = table.cellAt(0, 1).lastCursorPosition()
        start.setPosition(end.position(), appmod.QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(start)
        self.window.merge_selected_table_cells()
        merged_cell = table.cellAt(0, 0)
        self.assertEqual((merged_cell.rowSpan(), merged_cell.columnSpan()), (1, 2))

        editor.setTextCursor(merged_cell.firstCursorPosition())
        self.window.split_current_table_cell()
        self.assertEqual((table.cellAt(0, 0).rowSpan(), table.cellAt(0, 0).columnSpan()), (1, 1))


if __name__ == "__main__":
    unittest.main()
