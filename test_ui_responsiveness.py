"""Regression checks for hot-path UI work and Windows console flashes."""
import os
import random
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import erica_secure_text_editor as appmod


class ResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = appmod.QApplication.instance() or appmod.QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(appmod, "CONFIG_PATH", self.directory.name),
            patch.object(appmod, "CONFIG_FILE", os.path.join(self.directory.name, "config.json")),
            patch.object(appmod, "RECOVERY_FILE", os.path.join(self.directory.name, "recovery.enc")),
            patch.object(appmod, "_TEST_HARDEN_PRIVATE_FILE_HOOK", lambda path: None),
            patch.object(appmod, "_TEST_RECOVERY_KEY_PROTECTOR", lambda key: key),
            patch.object(appmod, "_TEST_RECOVERY_KEY_UNPROTECTOR", lambda key: key),
        ]
        for item in self.patches:
            item.start()
        self.window = appmod.MainWindow()

    def tearDown(self):
        self.window.current_editor.clear()
        self.window.close()
        for item in reversed(self.patches):
            item.stop()
        self.directory.cleanup()

    def test_cursor_navigation_does_not_serialize_or_split_document(self):
        editor = self.window.current_editor
        editor.setPlainText("one two three\n" * 1000)
        with patch.object(editor, "toPlainText", wraps=editor.toPlainText) as serialize:
            for position in range(50):
                cursor = editor.textCursor()
                cursor.setPosition(position)
                editor.setTextCursor(cursor)
            self.assertEqual(serialize.call_count, 0)
        self.assertIn("Words: 3000", self.window.status.currentMessage())

    def test_acl_subprocess_cannot_create_a_console_window(self):
        path = os.path.join(self.directory.name, "private.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{}")
        with patch.object(appmod, "_TEST_HARDEN_PRIVATE_FILE_HOOK", None), \
             patch.object(appmod.subprocess, "run") as run:
            appmod.harden_private_file(path)
        self.assertEqual(run.call_args.kwargs.get("creationflags", 0) &
                         appmod.subprocess.CREATE_NO_WINDOW,
                         appmod.subprocess.CREATE_NO_WINDOW)

    def assert_word_count(self):
        editor = self.window.current_editor
        self.assertEqual(editor.word_counter.total, len(editor.toPlainText().split()))
        self.assertEqual(len(editor.word_counter.counts), editor.document().blockCount())

    def test_counts_track_multiline_edits_undo_redo_and_unicode(self):
        editor = self.window.current_editor
        editor.setPlainText("one two\nthree\n\nlast\u00a0word 😀")
        self.assert_word_count()
        cursor = editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(15, appmod.QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText("new\nwords\n")
        self.assert_word_count()
        editor.undo()
        self.assert_word_count()
        editor.redo()
        self.assert_word_count()
        editor.selectAll()
        editor.insertPlainText("replacement")
        self.assert_word_count()
        editor.clear()
        self.assert_word_count()

    def test_counts_track_tables_and_rich_text(self):
        editor = self.window.current_editor
        editor.setHtml("<p>Before text</p><table><tr><td>one two</td><td>three</td></tr></table><p>After</p>")
        self.assert_word_count()
        cursor = editor.textCursor()
        cursor.movePosition(appmod.QTextCursor.MoveOperation.End)
        cursor.insertText(" more")
        self.assert_word_count()
        editor.selectAll()
        editor.setFontWeight(appmod.QFont.Weight.Bold)
        self.assert_word_count()

    def test_typing_only_counts_changed_block(self):
        editor = self.window.current_editor
        editor.setPlainText("one two three\n" * 1000)
        import erica_wordcount
        with patch.object(erica_wordcount, "count_words", wraps=erica_wordcount.count_words) as count:
            editor.insertPlainText("new ")
        self.assertLessEqual(count.call_count, 2)
        self.assert_word_count()

    def test_seeded_random_edits_keep_counts_exact(self):
        editor = self.window.current_editor
        randomizer = random.Random(17)
        for _ in range(300):
            cursor = editor.textCursor()
            length = editor.document().characterCount() - 1
            cursor.setPosition(randomizer.randrange(length + 1))
            cursor.setPosition(randomizer.randrange(length + 1), appmod.QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(randomizer.choice(["a b", "\n", "one\ntwo", "\u00a0", "😀", ""]))
            self.assert_word_count()

    def test_tab_switch_preserves_text_signal_connections_and_counts(self):
        first = self.window.current_editor
        first.setPlainText("first tab")
        self.window.add_new_tab(content="second")
        second = self.window.current_editor
        for _ in range(3):
            self.window.tabs.setCurrentIndex(0)
            self.assertIn("Words: 2", self.window.status.currentMessage())
            self.window.tabs.setCurrentIndex(1)
            self.assertIn("Words: 1", self.window.status.currentMessage())
        second.insertPlainText("new ")
        self.assertIn("Words: 2", self.window.status.currentMessage())
        self.assert_word_count()
        first.clear()

    def test_save_and_open_use_workers_while_gui_heartbeat_continues(self):
        path = os.path.join(self.directory.name, "worker.erica")
        self.window.current_editor.setPlainText("protected worker content")
        main_thread = threading.get_ident()
        threads = []
        beats = []
        timer = appmod.QTimer()
        timer.timeout.connect(lambda: beats.append(True))
        timer.start(5)
        encrypt = appmod.encrypt_text
        decrypt = appmod.decrypt_text

        def slow_encrypt(*args):
            threads.append(threading.get_ident())
            time.sleep(.08)
            return encrypt(*args)

        def record_decrypt(*args):
            threads.append(threading.get_ident())
            return decrypt(*args)

        with patch.object(self.window, "prompt_password", return_value="Passw0rd!"), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(path, "")), \
             patch.object(appmod.QMessageBox, "question", return_value=appmod.QMessageBox.StandardButton.No), \
             patch.object(appmod, "encrypt_text", side_effect=slow_encrypt), \
             patch.object(appmod, "decrypt_text", side_effect=record_decrypt):
            self.window.save_as_file()
            self.window.current_editor.clear()
            self.window.set_current_file_path(None)
            self.window.open_file(path)
        timer.stop()
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(thread != main_thread for thread in threads))
        self.assertGreaterEqual(len(beats), 2)
        self.assertIn("protected worker content", self.window.current_editor.toPlainText())
        self.assertTrue(self.window.isEnabled())
        self.assertTrue(self.window.timeout_timer.isActive())
        self.assertIsNone(self.window.get_current_password())

    def test_busy_file_operation_rejects_close_until_worker_finishes(self):
        observations = []

        def try_close():
            observations.append(self.window.close())
            observations.append(self.window._file_task_running)

        appmod.QTimer.singleShot(10, try_close)
        self.window._run_file_task(lambda: time.sleep(.08))
        self.assertEqual(observations, [False, True])
        self.assertFalse(self.window._file_task_running)
        self.assertTrue(self.window.timeout_timer.isActive())

    def test_failed_worker_restores_timer_and_keeps_unsaved_document(self):
        self.window.current_editor.setPlainText("must remain unsaved")
        self.window.current_editor.document().setModified(True)

        def fail():
            raise OSError("simulated write failure")

        with self.assertRaisesRegex(OSError, "simulated write failure"):
            self.window._run_file_task(fail)
        self.assertFalse(self.window._file_task_running)
        self.assertTrue(self.window.isEnabled())
        self.assertTrue(self.window.timeout_timer.isActive())
        self.assertTrue(self.window.current_editor.document().isModified())
        self.assertIn("must remain unsaved", self.window.current_editor.toPlainText())


if __name__ == "__main__":
    unittest.main()