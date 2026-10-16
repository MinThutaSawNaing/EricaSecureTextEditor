import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import erica_secure_text_editor as appmod


class RecoveryBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = appmod.QApplication.instance() or appmod.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(appmod, "CONFIG_PATH", self.temp.name),
            patch.object(appmod, "CONFIG_FILE", os.path.join(self.temp.name, "config.json")),
            patch.object(appmod, "RECOVERY_FILE", os.path.join(self.temp.name, "recovery.enc")),
            patch.object(appmod, "_TEST_RECOVERY_KEY_PROTECTOR", lambda s: "protected::" + s),
            patch.object(appmod, "_TEST_RECOVERY_KEY_UNPROTECTOR", lambda s: s.split("::", 1)[1]),
            patch.object(appmod, "_TEST_HARDEN_PRIVATE_FILE_HOOK", lambda p: None),
        ]
        for p in self.patches:
            p.start()
        self.window = appmod.MainWindow()
        self.window.recovery_timer.stop()
        self.window.current_editor.setPlainText("recover me")

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), "background recovery timed out")

    def read_snapshot(self):
        with open(appmod.RECOVERY_FILE, "rb") as handle:
            return handle.read()

    def test_actual_timer_encrypts_off_main_thread(self):
        threads = []
        encrypt = appmod.encrypt_bytes

        def record(*args):
            threads.append(threading.get_ident())
            return encrypt(*args)

        with patch.object(appmod, "encrypt_bytes", side_effect=record):
            self.window.recovery_timer.setSingleShot(True)
            self.window.recovery_timer.start(1)
            self.wait_for(lambda: os.path.exists(appmod.RECOVERY_FILE))
            self.assertEqual(len(threads), 1)
            self.assertNotEqual(threads[0], threading.get_ident())

    def test_actual_timer_does_not_rewrite_unchanged_snapshot(self):
        self.window.recovery_timer.timeout.emit()
        self.wait_for(lambda: os.path.exists(appmod.RECOVERY_FILE))
        first = self.read_snapshot()
        # Explicit autosave drains any completion notification before comparing.
        self.window.autosave_recovery_snapshot()
        self.window.recovery_timer.timeout.emit()
        self.window.autosave_recovery_snapshot()
        self.assertEqual(self.read_snapshot(), first)

    def test_unchanged_timer_does_not_serialize_html(self):
        self.window.autosave_recovery_snapshot()
        with patch.object(self.window.current_editor, "toHtml", side_effect=AssertionError("unchanged HTML capture")) as capture:
            self.window.recovery_timer.timeout.emit()
            capture.assert_not_called()

    def test_signature_invalidates_for_edits_formatting_path_tabs_and_undo(self):
        editor = self.window.current_editor
        self.window.autosave_recovery_snapshot()

        def verify_capture(change):
            change()
            with patch.object(editor, "toHtml", wraps=editor.toHtml) as capture:
                self.window.recovery_timer.timeout.emit()
                self.window.autosave_recovery_snapshot()
                self.assertGreater(capture.call_count, 0)

        verify_capture(lambda: editor.insertPlainText(" changed"))
        verify_capture(editor.undo)
        verify_capture(editor.redo)
        verify_capture(editor.undo)
        verify_capture(lambda: editor.insertPlainText(" branch"))

        def format_text():
            cursor = editor.textCursor()
            cursor.select(appmod.QTextCursor.SelectionType.Document)
            fmt = appmod.QTextCharFormat()
            fmt.setFontItalic(True)
            cursor.mergeCharFormat(fmt)

        verify_capture(format_text)
        verify_capture(lambda: self.window.open_documents[0].update(path="changed.erica"))
        verify_capture(lambda: self.window.add_new_tab(content="second tab"))
        verify_capture(lambda: self.window.open_documents.pop())
        # A saved file becomes ineligible when unmodified, and eligible again later.
        editor.document().setModified(False)
        self.window.recovery_timer.timeout.emit()
        editor.document().setModified(True)
        editor.insertPlainText(" eligible again")
        verify_capture(lambda: None)

    def test_timer_does_not_overlap_and_clear_invalidates_pending_write(self):
        entered = threading.Event()
        release = threading.Event()
        encrypt = appmod.encrypt_bytes
        calls = []

        def blocked(*args):
            calls.append(threading.get_ident())
            entered.set()
            release.wait(5)
            return encrypt(*args)

        with patch.object(appmod, "encrypt_bytes", side_effect=blocked):
            try:
                self.window.recovery_timer.timeout.emit()
                self.wait_for(entered.is_set)
                heartbeat = []
                appmod.QTimer.singleShot(0, lambda: heartbeat.append(True))
                self.wait_for(lambda: bool(heartbeat))
                self.window.current_editor.setPlainText("new version")
                for _ in range(5):
                    self.window.recovery_timer.timeout.emit()
                self.window.clear_recovery_snapshot()
            finally:
                release.set()
            self.window.autosave_recovery_snapshot()
            self.assertEqual(len(calls), 2)
        recovered = appmod.decrypt_bytes(self.read_snapshot(), appmod.get_recovery_key())
        self.assertIn(b"new version", recovered)

    def test_clear_does_not_allow_pending_job_to_recreate_file(self):
        entered = threading.Event()
        release = threading.Event()
        encrypt = appmod.encrypt_bytes

        def blocked(*args):
            entered.set()
            release.wait(5)
            return encrypt(*args)

        with patch.object(appmod, "encrypt_bytes", side_effect=blocked):
            try:
                self.window.recovery_timer.timeout.emit()
                self.wait_for(entered.is_set)
                self.window.clear_recovery_snapshot()
            finally:
                release.set()
            # An empty workspace must not replace the invalidated snapshot.
            self.window.current_editor.clear()
            self.window.autosave_recovery_snapshot()
        self.assertFalse(os.path.exists(appmod.RECOVERY_FILE))

    def test_close_waits_for_pending_job_then_writes_latest_snapshot(self):
        entered = threading.Event()
        release = threading.Event()
        encrypt = appmod.encrypt_bytes

        def blocked(*args):
            entered.set()
            release.wait(5)
            return encrypt(*args)

        with patch.object(appmod, "encrypt_bytes", side_effect=blocked):
            try:
                self.window.recovery_timer.timeout.emit()
                self.wait_for(entered.is_set)
                self.window.current_editor.setPlainText("final close version")
                threading.Timer(.05, release.set).start()
                self.window.close()
            finally:
                release.set()
        recovered = appmod.decrypt_bytes(self.read_snapshot(), appmod.get_recovery_key())
        self.assertIn(b"final close version", recovered)
        self.assertFalse(self.window.recovery_timer.isActive())

    def test_write_and_hardening_run_off_main_thread_and_failure_retries(self):
        threads = []
        write = appmod.atomic_write

        def record_write(*args, **kwargs):
            if args[0] == appmod.RECOVERY_FILE:
                threads.append(threading.get_ident())
            return write(*args, **kwargs)

        appmod.get_recovery_key()  # Separate config hardening from recovery work.
        with patch.object(appmod, "atomic_write", side_effect=record_write), patch.object(
            appmod, "_TEST_HARDEN_PRIVATE_FILE_HOOK",
            side_effect=lambda path: threads.append(threading.get_ident())
        ):
            self.window.recovery_timer.timeout.emit()
            self.window.autosave_recovery_snapshot()
        self.assertEqual(len(threads), 2)
        self.assertTrue(all(t != threading.get_ident() for t in threads))
        self.window.current_editor.setPlainText("retry content")
        with patch.object(appmod, "encrypt_bytes", side_effect=ValueError("failure")):
            self.window.recovery_timer.timeout.emit()
            self.window.autosave_recovery_snapshot()
        self.window.recovery_timer.timeout.emit()
        self.window.autosave_recovery_snapshot()
        self.assertIn(b"retry content", appmod.decrypt_bytes(self.read_snapshot(), appmod.get_recovery_key()))