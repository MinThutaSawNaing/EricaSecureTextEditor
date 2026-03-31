import os
import tempfile
import unittest
from unittest.mock import patch

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
        self.window = appmod.MainWindow()

    def tearDown(self):
        self.window.close()
        self.temp_dir.cleanup()

    def test_encrypt_roundtrip(self):
        encrypted = appmod.encrypt_text("hello", "Passw0rd!")
        self.assertEqual(appmod.decrypt_text(encrypted, "Passw0rd!"), "hello")

    def test_recent_files_and_last_session(self):
        test_file = os.path.join(self.temp_dir.name, "sample.enc")
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

    def test_save_and_resave_same_file(self):
        fd, path = tempfile.mkstemp(dir=self.temp_dir.name, suffix=".enc")
        os.close(fd)
        os.unlink(path)

        with patch.object(appmod.QMessageBox, "question", return_value=appmod.QMessageBox.StandardButton.No), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(path, "Encrypted Files (*.enc)")):
            self.window.prompt_password = lambda *args, **kwargs: "Passw0rd!"
            self.window.current_editor.setPlainText("first")
            self.window.save_as_file()
            self.window.current_editor.setPlainText("second")
            self.window.save_file()

        with open(path, "rb") as handle:
            decrypted = appmod.decrypt_text(handle.read(), "Passw0rd!")
        self.assertIn("second", decrypted)

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
