"""Offscreen organization-mode integration tests.

Run: python -m unittest -v test_organization_workflows
Organization enrollment uses real Windows current-user DPAPI. Only the unrelated
workspace recovery-key protector is replaced; no organization crypto is mocked.
"""

import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QMessageBox

import erica_organization as organization
import erica_organization_ui as orgui
import erica_secure_text_editor as appmod


TOKENS = ("0123456789012345", "9876543210987654")
OTHER_TOKENS = ("1111222233334444", "5555666677778888")
CHECKS = tuple(map(organization.check_value, TOKENS))
PASSWORD = "Legacy-test-password-123!"


def fill_dialog(dialog, tokens=TOKENS, checks=CHECKS, backed_up=True):
    for field, value in zip(dialog.token_inputs, tokens):
        field.setText(value)
    for field, value in zip(dialog.check_inputs, checks):
        field.setText(value)
    dialog.backed_up.setChecked(backed_up)


class QtTestCase(unittest.TestCase):
    def enterContext(self, context):
        """unittest.enterContext equivalent, also supported on Python 3.10."""
        result = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return result

    @classmethod
    def setUpClass(cls):
        cls.app = appmod.QApplication.instance() or appmod.QApplication([])


class OrganizationDialogTests(QtTestCase):
    def setUp(self):
        self.dialog = orgui.OrganizationTokenDialog()
        self.warning = self.enterContext(patch.object(orgui.QMessageBox, "warning"))

    def tearDown(self):
        self.dialog.clear_fields()
        self.dialog.close()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_tokens_are_masked_and_visibility_toggle_is_reversible(self):
        fill_dialog(self.dialog)
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Password
                            for field in self.dialog.token_inputs))
        self.dialog.show_tokens.setChecked(True)
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Normal
                            for field in self.dialog.token_inputs))
        self.dialog.show_tokens.setChecked(False)
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Password
                            for field in self.dialog.token_inputs))
        self.assertEqual(tuple(field.text() for field in self.dialog.token_inputs), TOKENS)

    def test_checks_are_automatic_read_only_and_cannot_be_typed_or_pasted(self):
        fill_dialog(self.dialog)
        clipboard = self.app.clipboard()
        try:
            for field, expected in zip(self.dialog.check_inputs, CHECKS):
                self.assertTrue(field.isReadOnly())
                field.selectAll()
                QTest.keyClicks(field, "00000")
                self.assertEqual(field.text(), expected)
                clipboard.setText("99999")
                QTest.keyClick(field, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(field.text(), expected)
        finally:
            clipboard.clear()

    def test_token_edits_refresh_checks_clear_invalid_values_and_reset_backup(self):
        fill_dialog(self.dialog)
        self.dialog.token_inputs[0].setText(OTHER_TOKENS[0])
        self.assertEqual(self.dialog.check_inputs[0].text(), organization.check_value(OTHER_TOKENS[0]))
        self.assertFalse(self.dialog.backed_up.isChecked())
        self.dialog.token_inputs[0].setText("123")
        self.assertEqual(self.dialog.check_inputs[0].text(), "")
        self.assertFalse(self.dialog.copy_buttons[0].isEnabled())
        self.assertEqual(self.dialog.check_inputs[1].text(), CHECKS[1])
        self.dialog.token_inputs[0].setText(TOKENS[0])
        self.assertEqual(self.dialog.check_inputs[0].text(), CHECKS[0])
        self.assertTrue(self.dialog.copy_buttons[0].isEnabled())

    def test_copy_buttons_copy_only_corresponding_check_without_accepting_dialog(self):
        self.assertTrue(all(not button.isEnabled() for button in self.dialog.copy_buttons))
        fill_dialog(self.dialog)
        clipboard = self.app.clipboard()
        try:
            for button, expected in zip(self.dialog.copy_buttons, CHECKS):
                self.assertTrue(button.isEnabled())
                self.assertFalse(button.autoDefault())
                self.assertTrue(button.accessibleName())
                button.click()
                self.assertEqual(clipboard.text(), expected)
                self.assertIsNone(self.dialog.tokens)
                self.assertNotEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
            self.dialog.clear_fields()
            self.assertTrue(all(not button.isEnabled() for button in self.dialog.copy_buttons))
        finally:
            clipboard.clear()

    def test_invalid_tokens_and_checks_cannot_accept(self):
        cases = [(("123", TOKENS[1]), CHECKS),
                 (("０" * 16, TOKENS[1]), CHECKS),
                 ((TOKENS[0], TOKENS[0]), (CHECKS[0], CHECKS[0])),
                 (TOKENS, CHECKS[::-1]), (TOKENS, ("00000", CHECKS[1])),
                 (TOKENS, ("ABCDE", CHECKS[1])), (TOKENS, ("123456", CHECKS[1]))]
        for tokens, checks in cases:
            with self.subTest(tokens=tokens, checks=checks):
                self.warning.reset_mock()
                fill_dialog(self.dialog, tokens, checks)
                self.dialog.validate_and_accept()
                self.warning.assert_called_once()
                self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
                self.assertIsNone(self.dialog.tokens)

    def test_secure_backup_acknowledgement_is_required(self):
        fill_dialog(self.dialog, backed_up=False)
        self.dialog.validate_and_accept()
        self.warning.assert_called_once()
        self.assertIn("backed up", self.warning.call_args.args[2].lower())
        self.assertIsNone(self.dialog.tokens)
        self.dialog.backed_up.setChecked(True)
        self.dialog.validate_and_accept()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.dialog.tokens, TOKENS)

    def test_generate_produces_valid_pair_checks_and_resets_backup_consent(self):
        fill_dialog(self.dialog)
        self.dialog.generate_pair()
        tokens = tuple(field.text() for field in self.dialog.token_inputs)
        checks = tuple(field.text() for field in self.dialog.check_inputs)
        self.assertEqual(organization.validate_tokens(*tokens), tokens)
        self.assertEqual(checks, tuple(map(organization.check_value, tokens)))
        for check in checks:
            self.assertRegex(check, r"\A[0-9]{5}\Z")
        self.assertFalse(self.dialog.backed_up.isChecked())
        self.assertTrue(self.dialog.show_tokens.isChecked())
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Normal
                            for field in self.dialog.token_inputs))
        self.dialog.show_tokens.setChecked(False)
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Password
                            for field in self.dialog.token_inputs))
        self.dialog.generate_pair()
        self.assertTrue(self.dialog.show_tokens.isChecked())
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Normal
                            for field in self.dialog.token_inputs))
        self.dialog.validate_and_accept()
        self.assertIsNone(self.dialog.tokens)

    def test_failed_generation_does_not_reveal_or_replace_existing_tokens(self):
        for visible in (False, True):
            with self.subTest(visible=visible):
                fill_dialog(self.dialog)
                self.dialog.show_tokens.setChecked(visible)
                self.warning.reset_mock()
                with patch.object(organization, "generate_tokens", side_effect=RuntimeError("Generation failed")):
                    self.dialog.generate_pair()
                self.warning.assert_called_once()
                self.assertEqual(self.dialog.show_tokens.isChecked(), visible)
                self.assertEqual(tuple(field.text() for field in self.dialog.token_inputs), TOKENS)
                self.assertTrue(self.dialog.backed_up.isChecked())
                expected = QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
                self.assertTrue(all(field.echoMode() == expected for field in self.dialog.token_inputs))

    def test_show_tokens_indicator_is_visible_in_both_themes_and_keyboard_operable(self):
        from PyQt6.QtGui import QColor

        for theme, mark, fill in (("dark", "#182337", "#8AB4F8"),
                                  ("light", "#FFFFFF", "#245EA8")):
            dialog = orgui.OrganizationTokenDialog(theme=theme)
            try:
                fill_dialog(dialog)
                dialog.show()
                self.app.processEvents()
                toggle = dialog.show_tokens
                self.assertFalse(toggle.isChecked())
                option = orgui.QStyleOptionButton()
                toggle.initStyleOption(option)
                rect = toggle.style().subElementRect(orgui.QStyle.SubElement.SE_CheckBoxIndicator,
                                                    option, toggle)
                self.assertGreaterEqual(rect.width(), 18)
                unchecked = toggle.grab().toImage()
                toggle.setFocus()
                QTest.keyClick(toggle, Qt.Key.Key_Space)
                self.assertTrue(toggle.isChecked())
                self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Normal
                                    for field in dialog.token_inputs))
                checked = toggle.grab().toImage()
                scale = checked.devicePixelRatio()
                # The indicator must contain both its contrasting fill and a real checkmark.
                pixels = [checked.pixelColor(x, y).name().upper()
                          for x in range(int(rect.left() * scale), int((rect.right() + 1) * scale))
                          for y in range(int(rect.top() * scale), int((rect.bottom() + 1) * scale))]
                self.assertIn(QColor(mark).name().upper(), pixels)
                self.assertIn(QColor(fill).name().upper(), pixels)
                self.assertNotEqual(unchecked, checked)
                QTest.keyClick(toggle, Qt.Key.Key_Space)
                self.assertFalse(toggle.isChecked())
                self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Password
                                    for field in dialog.token_inputs))
            finally:
                dialog.clear_fields()
                dialog.close()
                dialog.deleteLater()

    def test_inline_warning_requires_sixteen_digits_and_clears_when_corrected(self):
        for hint in self.dialog.token_warnings:
            self.assertIn("exactly 16 digits", hint.text())
            self.assertEqual(hint.property("status"), "hint")
        for value in ("123", "0" * 17, "a" * 16, "０" * 16):
            with self.subTest(value=value):
                self.dialog.token_inputs[0].setText(value)
                self.assertIn("Warning", self.dialog.token_warnings[0].text())
                self.assertIn("exactly 16 digits", self.dialog.token_warnings[0].text())
                self.assertEqual(self.dialog.token_warnings[0].property("status"), "error")
                self.assertTrue(self.dialog.token_inputs[0].property("invalid"))
                self.assertEqual(self.dialog.token_inputs[0].text(), value)
                self.assertFalse(self.dialog.copy_buttons[0].isEnabled())
        self.dialog.token_inputs[0].setText(TOKENS[0])
        self.assertEqual(self.dialog.token_warnings[0].property("status"), "ready")
        self.assertFalse(self.dialog.token_inputs[0].property("invalid"))
        self.assertEqual(self.dialog.check_inputs[0].text(), CHECKS[0])
        self.dialog.token_inputs[0].clear()
        self.assertEqual(self.dialog.token_warnings[0].property("status"), "hint")

    def test_warning_on_save_mentions_exactly_sixteen_digits(self):
        self.dialog.token_inputs[0].setText("123")
        self.dialog.validate_and_accept()
        self.warning.assert_called_once()
        self.assertIn("exactly 16", self.warning.call_args.args[2])
        self.assertIsNone(self.dialog.tokens)

    def test_compact_dialog_supports_light_dark_and_parent_theme(self):
        for mode, background, surface in (("dark", "#252526", "#303033"),
                                          ("light", "#F0F0F0", "#FFFFFF")):
            dialog = orgui.OrganizationTokenDialog(theme=mode)
            try:
                self.assertEqual(dialog.property("ericaTheme"), mode)
                self.assertIn(background, dialog.styleSheet())
                self.assertIn(surface, dialog.styleSheet())
                self.assertNotIn("organizationHeader", dialog.styleSheet())
                self.assertNotIn("organizationCard", dialog.styleSheet())
                self.assertEqual(len(dialog.findChildren(orgui.QFormLayout)), 1)
                self.assertLessEqual(dialog.width(), 680)
                for field in dialog.check_inputs:
                    self.assertTrue(field.isReadOnly())
                child = orgui.OrganizationTokenDialog(dialog)
                try:
                    self.assertEqual(child.property("ericaTheme"), mode)
                finally:
                    child.close()
                    child.deleteLater()
            finally:
                dialog.close()
                dialog.deleteLater()

    def test_save_cancel_buttons_and_explicit_clear(self):
        fill_dialog(self.dialog)
        buttons = self.dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).click()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Rejected)
        self.assertIsNone(self.dialog.tokens)
        buttons.button(QDialogButtonBox.StandardButton.Save).click()
        self.assertEqual(self.dialog.tokens, TOKENS)
        self.dialog.clear_fields()
        self.assertIsNone(self.dialog.tokens)
        self.assertTrue(all(not field.text() for field in
                            self.dialog.token_inputs + self.dialog.check_inputs))


class OrganizationWarningThemeTests(QtTestCase):
    def test_real_warning_popup_is_legible_with_opposite_system_theme(self):
        original_palette = QPalette(self.app.palette())
        original_stylesheet = self.app.styleSheet()
        try:
            for theme, background, foreground, system_background, system_foreground in (
                ("light", "#f0f0f0", "#202124", "#202020", "#f0f0f0"),
                ("dark", "#252526", "#f0f0f0", "#f0f0f0", "#202020"),
            ):
                with self.subTest(theme=theme):
                    palette = QPalette(original_palette)
                    palette.setColor(QPalette.ColorRole.Window, QColor(system_background))
                    palette.setColor(QPalette.ColorRole.WindowText, QColor(system_foreground))
                    self.app.setPalette(palette)
                    self.app.setStyleSheet(
                        f"QMessageBox {{ background: {system_background}; color: {system_foreground}; }}"
                    )
                    dialog = orgui.OrganizationTokenDialog(theme=theme)
                    snapshots = []

                    def inspect_and_close():
                        popup = self.app.activeModalWidget()
                        if isinstance(popup, QMessageBox):
                            popup.ensurePolished()
                            message = popup.findChild(QLabel, "qt_msgbox_label")
                            button = popup.button(QMessageBox.StandardButton.Ok)
                            snapshots.append((
                                popup.text(),
                                popup.palette().color(QPalette.ColorRole.Window).name(),
                                message.palette().color(QPalette.ColorRole.WindowText).name(),
                                button.palette().color(QPalette.ColorRole.ButtonText).name(),
                            ))
                            popup.accept()
                        elif popup is not None:
                            popup.reject()

                    try:
                        # Exercise real static QMessageBox calls, not mocked warnings.
                        for trigger in (dialog.validate_and_accept, dialog.generate_pair):
                            with patch.object(organization, "generate_tokens", side_effect=OSError("Token generation unavailable.")):
                                QTimer.singleShot(0, inspect_and_close)
                                trigger()
                        self.assertEqual(len(snapshots), 2)
                        for message, actual_background, actual_text, actual_button_text in snapshots:
                            self.assertTrue(message)
                            self.assertEqual(actual_background, background)
                            self.assertEqual(actual_text, foreground)
                            self.assertEqual(actual_button_text, foreground)
                        self.assertIsNone(dialog.tokens)
                        self.assertFalse(dialog.show_tokens.isChecked())
                    finally:
                        dialog.close()
                        dialog.deleteLater()
        finally:
            self.app.setStyleSheet(original_stylesheet)
            self.app.setPalette(original_palette)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@unittest.skipUnless(os.name == "nt", "Real Windows current-user DPAPI required")
class OrganizationWorkflowTests(QtTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="erica-org-workflows-")
        self.root = Path(self.temporary.name)
        self.windows = []
        self.config_dir = self.root / "account-a"
        self.config_dir.mkdir()
        for name, value in self.config_values(self.config_dir).items():
            self.enterContext(patch.object(appmod, name, value))
        # These hooks are exclusively for recovery, not organization DPAPI.
        self.enterContext(patch.object(appmod, "_TEST_RECOVERY_KEY_PROTECTOR",
                                      lambda secret: "test-recovery::" + secret))
        self.enterContext(patch.object(appmod, "_TEST_RECOVERY_KEY_UNPROTECTOR",
                                      lambda value: value.split("test-recovery::", 1)[1]))
        self.hardened = []
        self.enterContext(patch.object(appmod, "_TEST_HARDEN_PRIVATE_FILE_HOOK", self.hardened.append))
        self.critical = self.enterContext(patch.object(appmod.QMessageBox, "critical"))
        self.warning = self.enterContext(patch.object(appmod.QMessageBox, "warning"))
        self.enterContext(patch.object(appmod.QMessageBox, "information"))
        self.question = self.enterContext(patch.object(
            appmod.QMessageBox, "question", return_value=appmod.QMessageBox.StandardButton.No))
        self.password_prompt = self.enterContext(patch.object(
            appmod.MainWindow, "prompt_password", side_effect=AssertionError("Unexpected password prompt")))

    @staticmethod
    def config_values(directory):
        return {"CONFIG_PATH": str(directory), "CONFIG_FILE": str(directory / "config.json"),
                "RECOVERY_FILE": str(directory / "recovery.enc")}

    @contextmanager
    def config_scope(self, directory):
        from contextlib import ExitStack
        directory.mkdir(exist_ok=True)
        with ExitStack() as stack:
            for name, value in self.config_values(directory).items():
                stack.enter_context(patch.object(appmod, name, value))
            yield

    def new_window(self, directory=None):
        directory = directory or self.config_dir
        with self.config_scope(directory):
            window = appmod.MainWindow()
        # Keep tests deterministic; explicit file tasks still use the real Qt worker.
        window.timeout_timer.stop()
        window.recovery_timer.stop()
        self.windows.append((window, directory))
        return window

    def close_window(self, window):
        pair = next(pair for pair in self.windows if pair[0] is window)
        with self.config_scope(pair[1]):
            window.close()
            window.timeout_timer.stop()
            window.recovery_timer.stop()
            window.clipboard_clear_timer.stop()
        self.windows.remove(pair)
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def tearDown(self):
        try:
            for window, _ in list(self.windows):
                self.close_window(window)
        finally:
            # Encrypted files are intentionally read-only, including on Windows.
            for directory, _, filenames in os.walk(self.root):
                for filename in filenames:
                    os.chmod(os.path.join(directory, filename), stat.S_IREAD | stat.S_IWRITE)
            self.temporary.cleanup()

    def enroll(self, tokens=TOKENS):
        appmod.save_organization_tokens(tokens, tuple(map(organization.check_value, tokens)))

    def save_as(self, window, path):
        with patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            window.save_as_file()

    def assert_no_errors_or_passwords(self):
        self.critical.assert_not_called()
        self.warning.assert_not_called()
        self.password_prompt.assert_not_called()

    def test_passwordless_save_as_open_resave_and_silent_save(self):
        self.enroll()
        window = self.new_window()
        path = self.root / "organization.erica"
        window.current_editor.setPlainText("Organization first version Ω")
        self.save_as(window, path)
        self.assertEqual(window.current_file_path, str(path))
        self.assertTrue(appmod.file_uses_organization(path))
        self.assertIn("first version Ω", appmod.read_encrypted_document(path, TOKENS))
        first = path.read_bytes()
        window.current_editor.setPlainText("Organization resaved version")
        window.save_file()
        self.assertFalse(window.current_editor.document().isModified())
        self.assertNotEqual(first, path.read_bytes())
        self.assertIn("resaved version", appmod.read_encrypted_document(path, TOKENS))
        window.current_editor.setPlainText("Organization silent version")
        self.assertTrue(window.silent_save(window.tabs.currentIndex()))
        self.assertIn("silent version", appmod.read_encrypted_document(path, TOKENS))
        reader = self.new_window()
        reader.open_file(str(path))
        self.assertEqual(reader.current_editor.toPlainText(), "Organization silent version")
        self.assertEqual(reader.open_documents[0]["protection_mode"], "organization")
        for document in window.open_documents + reader.open_documents:
            self.assertIsNone(document.get("password"))
            self.assertNotIn("tokens", document)
        self.assert_no_errors_or_passwords()

    def test_passwordless_silent_save_of_untitled_document(self):
        self.enroll()
        window = self.new_window()
        window.current_editor.setPlainText("untitled org secret")
        path = self.root / "silent.erica"
        with patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(str(path), "")):
            self.assertTrue(window.silent_save(0))
        self.assertEqual(window.current_file_path, str(path))
        self.assertFalse(window.current_editor.document().isModified())
        self.assertIn("untitled org secret", appmod.read_encrypted_document(path, TOKENS))
        self.assert_no_errors_or_passwords()

    def test_passwordless_image_ui_roundtrip(self):
        self.enroll()
        window = self.new_window()
        source, encrypted, output = (self.root / name for name in ("original.png", "photo.eimg", "restored.png"))
        # A valid one-pixel PNG; image bytes must survive exactly, not be reencoded.
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
        source.write_bytes(raw)
        with patch.object(appmod.QFileDialog, "getOpenFileName", return_value=(str(source), "")), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(str(encrypted), "")):
            window.encrypt_image_file()
        self.assertTrue(appmod.file_uses_organization(encrypted))
        self.assertEqual(appmod.read_encrypted_image(encrypted, TOKENS), (".png", raw))
        with patch.object(appmod.QFileDialog, "getOpenFileName", return_value=(str(encrypted), "")), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(str(output), "")):
            window.decrypt_image_file()
        self.assertEqual(output.read_bytes(), raw)
        self.assert_no_errors_or_passwords()

    def test_independent_config_enrollments_can_open_same_document(self):
        self.enroll()
        blob_a = appmod.load_config()["organization_tokens_protected"]
        writer = self.new_window()
        writer.current_editor.setPlainText("Shared across independently enrolled profiles")
        path = self.root / "shared.erica"
        self.save_as(writer, path)
        second_dir = self.root / "account-b"
        with self.config_scope(second_dir):
            self.enroll()
            blob_b = appmod.load_config()["organization_tokens_protected"]
            self.assertNotEqual(blob_a, blob_b)
            reader = self.new_window(second_dir)
            reader.open_file(str(path))
            self.assertEqual(reader.current_editor.toPlainText(), writer.current_editor.toPlainText())
            self.assertEqual(appmod.get_organization_tokens(), TOKENS)
        self.assert_no_errors_or_passwords()

    def test_persistence_and_default_survive_window_restart(self):
        self.enroll()
        window = self.new_window()
        self.assertTrue(window.organization_mode_action.isChecked())
        self.close_window(window)
        restarted = self.new_window()
        self.assertEqual(appmod.get_organization_tokens(), TOKENS)
        self.assertEqual(restarted.encryption_mode, "organization")
        self.assertTrue(restarted.organization_mode_action.isChecked())
        restarted.current_editor.setPlainText("After restart")
        path = self.root / "restart.erica"
        self.save_as(restarted, path)
        self.assertIn("After restart", appmod.read_encrypted_document(path, TOKENS))
        self.assert_no_errors_or_passwords()

    def test_config_contains_only_dpapi_ciphertext_not_tokens_or_checks(self):
        appmod.save_config({"theme": "light", "unrelated_setting": 42})
        self.enroll()
        config = appmod.load_config()
        self.assertEqual(config["unrelated_setting"], 42)
        self.assertEqual(config["encryption_mode"], "organization")
        encoded = Path(appmod.CONFIG_FILE).read_bytes()
        blob = base64.b64decode(config["organization_tokens_protected"], validate=True)
        self.assertEqual(organization.unprotect_tokens(config["organization_tokens_protected"]), TOKENS)
        for secret in TOKENS + CHECKS:
            self.assertNotIn(secret.encode("ascii"), encoded)
            self.assertNotIn(secret.encode("ascii"), blob)
            self.assertNotIn(secret.encode("utf-16le"), blob)
        self.assertIn(appmod.CONFIG_FILE, self.hardened)

    def test_invalid_check_does_not_write_or_replace_configuration(self):
        self.enroll()
        before = Path(appmod.CONFIG_FILE).read_bytes()
        with patch.object(appmod, "save_config") as save, \
             patch.object(organization, "protect_tokens", wraps=organization.protect_tokens) as protect:
            with self.assertRaises(ValueError):
                appmod.save_organization_tokens(OTHER_TOKENS, CHECKS)
            save.assert_not_called()
            protect.assert_not_called()
        self.assertEqual(Path(appmod.CONFIG_FILE).read_bytes(), before)
        self.assertEqual(appmod.get_organization_tokens(), TOKENS)

    def test_wrong_tokens_refuse_open_without_changing_editor_or_file(self):
        path = self.root / "foreign.erica"
        appmod.write_encrypted_document(path, "<p>Original secret</p>", TOKENS)
        original = path.read_bytes()
        self.enroll(OTHER_TOKENS)
        window = self.new_window()
        window.current_editor.setPlainText("Keep unsaved work")
        before = window.current_editor.toHtml()
        window.open_file(str(path))
        self.critical.assert_called_once()
        self.assertEqual(window.current_editor.toHtml(), before)
        self.assertIsNone(window.current_file_path)
        self.assertEqual(window.tabs.count(), 1)
        self.assertEqual(path.read_bytes(), original)
        self.password_prompt.assert_not_called()

    def test_wrong_tokens_refuse_resave_silent_save_and_save_as_overwrite(self):
        self.enroll()
        path = self.root / "original.erica"
        appmod.write_encrypted_document(path, "<p>Original</p>", TOKENS)
        original = path.read_bytes()
        window = self.new_window()
        window.open_file(str(path))
        self.enroll(OTHER_TOKENS)
        window.current_editor.setPlainText("Must not overwrite original")
        window.current_editor.document().setModified(True)
        for operation in (window.save_file, lambda: window.silent_save(0),
                          lambda: self.save_as(window, path)):
            with self.subTest(operation=operation):
                self.critical.reset_mock()
                operation()
                self.critical.assert_called_once()
                self.assertEqual(path.read_bytes(), original)
                self.assertTrue(window.current_editor.document().isModified())
                self.assertEqual(window.current_file_path, str(path))
        self.password_prompt.assert_not_called()

    def test_direct_writers_refuse_wrong_tokens_and_cross_mode_overwrites(self):
        source = self.root / "source.png"
        source.write_bytes(b"image bytes")
        document, image, legacy = (self.root / name for name in ("doc.erica", "image.eimg", "legacy.erica"))
        appmod.write_encrypted_document(document, "<p>Original</p>", TOKENS)
        appmod.write_encrypted_image(source, image, TOKENS)
        appmod.write_encrypted_document(legacy, "<p>Legacy</p>", PASSWORD)
        for path, credential, writer in (
            (document, OTHER_TOKENS, lambda p, c: appmod.write_encrypted_document(p, "replacement", c)),
            (image, OTHER_TOKENS, lambda p, c: appmod.write_encrypted_image(source, p, c)),
            (document, PASSWORD, lambda p, c: appmod.write_encrypted_document(p, "replacement", c)),
            (image, PASSWORD, lambda p, c: appmod.write_encrypted_image(source, p, c)),
            (legacy, TOKENS, lambda p, c: appmod.write_encrypted_document(p, "replacement", c)),
        ):
            with self.subTest(path=path, credential_type=type(credential)):
                original = path.read_bytes()
                with self.assertRaises(ValueError):
                    appmod.verify_destination_mode(path, credential)
                with self.assertRaises(ValueError):
                    writer(path, credential)
                self.assertEqual(path.read_bytes(), original)

    def test_legacy_password_prompt_preserved_under_organization_default(self):
        path = self.root / "legacy.erica"
        appmod.write_encrypted_document(path, "<p>Legacy content</p>", PASSWORD)
        self.enroll()
        window = self.new_window()
        with patch.object(window, "prompt_password", return_value=PASSWORD) as prompt:
            window.open_file(str(path))
            prompt.assert_called_once_with("Decrypt File", show_strength=False)
            self.assertEqual(window.current_editor.toPlainText(), "Legacy content")
            self.assertEqual(window.open_documents[0]["protection_mode"], "password")
            window.current_editor.setPlainText("Legacy edited")
            window.save_file()
            self.assertEqual(prompt.call_count, 2)
            window.current_editor.setPlainText("Legacy silent")
            self.assertTrue(window.silent_save(0))
            self.assertEqual(prompt.call_count, 3)
        self.assertFalse(appmod.file_uses_organization(path))
        self.assertIn("Legacy silent", appmod.read_encrypted_document(path, PASSWORD))
        self.assertIsNone(window.get_current_password())
        self.assert_no_errors_or_passwords()

    def test_changing_default_does_not_convert_open_files(self):
        self.enroll()
        window = self.new_window()
        org_path, legacy_path = self.root / "org.erica", self.root / "password.erica"
        window.current_editor.setPlainText("Organization file")
        self.save_as(window, org_path)
        appmod.write_encrypted_document(legacy_path, "<p>Password file</p>", PASSWORD)
        with patch.object(window, "prompt_password", return_value=PASSWORD):
            window.open_file(str(legacy_path))
        before = (org_path.read_bytes(), legacy_path.read_bytes())
        window.set_encryption_mode("password")
        window.set_encryption_mode("organization")
        self.assertEqual(before, (org_path.read_bytes(), legacy_path.read_bytes()))
        self.assertEqual([doc["protection_mode"] for doc in window.open_documents],
                         ["organization", "password"])
        window.tabs.setCurrentIndex(0)
        window.set_encryption_mode("password")
        window.current_editor.setPlainText("Still organization")
        window.save_file()
        self.assertTrue(appmod.file_uses_organization(org_path))
        window.tabs.setCurrentIndex(1)
        window.set_encryption_mode("organization")
        window.current_editor.setPlainText("Still password")
        with patch.object(window, "prompt_password", return_value=PASSWORD) as prompt:
            window.save_file()
            prompt.assert_called_once()
        self.assertFalse(appmod.file_uses_organization(legacy_path))
        self.assert_no_errors_or_passwords()

    def test_explicit_save_as_new_name_uses_default_without_converting_original(self):
        self.enroll()
        old = self.root / "old-password.erica"
        appmod.write_encrypted_document(old, "<p>Explicit conversion copy</p>", PASSWORD)
        before = old.read_bytes()
        window = self.new_window()
        with patch.object(window, "prompt_password", return_value=PASSWORD):
            window.open_file(str(old))
        new = self.root / "new-org.erica"
        self.save_as(window, new)
        self.assertEqual(old.read_bytes(), before)
        self.assertTrue(appmod.file_uses_organization(new))
        self.assertIn("Explicit conversion copy", appmod.read_encrypted_document(new, TOKENS))
        self.assert_no_errors_or_passwords()

    def test_remove_tokens_preserves_old_files_and_fails_closed_on_resave(self):
        self.enroll()
        window = self.new_window()
        path = self.root / "retained.erica"
        window.current_editor.setPlainText("Keep original")
        self.save_as(window, path)
        original = path.read_bytes()
        appmod.remove_organization_tokens()
        self.assertNotIn("organization_tokens_protected", appmod.load_config())
        self.assertEqual(appmod.load_config()["encryption_mode"], "password")
        with self.assertRaises(ValueError):
            appmod.get_organization_tokens()
        window.set_encryption_mode("password")
        window.current_editor.setPlainText("Unsaved changes")
        window.current_editor.document().setModified(True)
        self.assertFalse(window.silent_save(0))
        self.critical.assert_called_once()
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(window.current_editor.document().isModified())
        self.password_prompt.assert_not_called()
        self.assertIn("Keep original", appmod.read_encrypted_document(path, TOKENS))

    def test_corrupt_dpapi_blob_fails_closed_for_open_and_new_save(self):
        self.enroll()
        path = self.root / "existing.erica"
        appmod.write_encrypted_document(path, "<p>Protected</p>", TOKENS)
        original = path.read_bytes()
        config = appmod.load_config()
        raw = bytearray(base64.b64decode(config["organization_tokens_protected"]))
        raw[len(raw) // 2] ^= 1
        config["organization_tokens_protected"] = base64.b64encode(raw).decode("ascii")
        appmod.save_config(config)
        before = Path(appmod.CONFIG_FILE).read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot be unlocked"):
            appmod.get_organization_tokens()
        self.assertEqual(Path(appmod.CONFIG_FILE).read_bytes(), before)
        window = self.new_window()
        window.open_file(str(path))
        self.assertIsNone(window.current_file_path)
        window.current_editor.setPlainText("Must remain unsaved")
        window.current_editor.document().setModified(True)
        new_path = self.root / "not-created.erica"
        self.save_as(window, new_path)
        self.assertEqual(self.critical.call_count, 2)
        self.assertFalse(new_path.exists())
        self.assertTrue(window.current_editor.document().isModified())
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(appmod.load_config()["organization_tokens_protected"], config["organization_tokens_protected"])
        self.password_prompt.assert_not_called()

    def test_missing_tokens_cannot_enable_organization_mode(self):
        window = self.new_window()
        before = appmod.load_config()
        window.set_encryption_mode("organization")
        self.warning.assert_called_once()
        self.assertEqual(window.encryption_mode, "password")
        self.assertTrue(window.password_mode_action.isChecked())
        self.assertEqual(appmod.load_config(), before)
        self.password_prompt.assert_not_called()

    def test_damaged_or_nonobject_config_is_not_overwritten(self):
        self.enroll()
        config_path = Path(appmod.CONFIG_FILE)
        valid = config_path.read_bytes()
        try:
            for damaged in (b'{"organization_tokens_protected":', b'[]', b'null', b'"wrong root"'):
                with self.subTest(damaged=damaged):
                    config_path.write_bytes(damaged)
                    self.assertEqual(appmod.load_config(), {})
                    with self.assertRaises(ValueError):
                        appmod.get_organization_tokens()
                    for operation in (lambda: appmod.save_config({"theme": "dark"}),
                                      self.enroll, appmod.remove_organization_tokens):
                        with self.assertRaisesRegex(ValueError, "not overwritten"):
                            operation()
                        self.assertEqual(config_path.read_bytes(), damaged)
        finally:
            config_path.write_bytes(valid)
        self.assertEqual(appmod.get_organization_tokens(), TOKENS)

    def test_disk_protection_mode_change_refuses_resave_without_prompt(self):
        self.enroll()
        window = self.new_window()
        for recorded, replacement in ((TOKENS, PASSWORD), (PASSWORD, TOKENS)):
            path = self.root / ("opened-org.erica" if isinstance(recorded, tuple) else "opened-password.erica")
            appmod.write_encrypted_document(path, "<p>Originally opened</p>", recorded)
            if isinstance(recorded, tuple):
                window.open_file(str(path))
            else:
                with patch.object(window, "prompt_password", return_value=PASSWORD):
                    window.open_file(str(path))
            # Simulate an external replacement after the document was opened.
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
            path.unlink()
            appmod.write_encrypted_document(path, "<p>Externally replaced</p>", replacement)
            original = path.read_bytes()
            window.current_editor.setPlainText("Unsaved local edits")
            window.current_editor.document().setModified(True)
            for save in (window.save_file, lambda: window.silent_save(window.tabs.currentIndex())):
                with self.subTest(recorded=type(recorded), operation=save):
                    self.critical.reset_mock()
                    save()
                    self.critical.assert_called_once()
                    self.assertIn("changed on disk", self.critical.call_args.args[2])
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(window.current_editor.document().isModified())
            self.password_prompt.assert_not_called()

    def test_organization_credential_failure_for_image_never_creates_output(self):
        self.enroll()
        source, encrypted, output = (self.root / name for name in ("input.png", "private.eimg", "no-output.png"))
        source.write_bytes(b"original image payload")
        appmod.write_encrypted_image(source, encrypted, TOKENS)
        original = encrypted.read_bytes()
        self.enroll(OTHER_TOKENS)
        window = self.new_window()
        with patch.object(appmod.QFileDialog, "getOpenFileName", return_value=(str(encrypted), "")), \
             patch.object(appmod.QFileDialog, "getSaveFileName", return_value=(str(output), "")) as save:
            window.decrypt_image_file()
            save.assert_not_called()
        self.critical.assert_called_once()
        self.assertFalse(output.exists())
        self.assertEqual(encrypted.read_bytes(), original)
        self.password_prompt.assert_not_called()

    def test_configure_dialog_accept_persists_and_clears_fields(self):
        window = self.new_window()
        dialogs = []

        def accept(dialog):
            dialogs.append(dialog)
            fill_dialog(dialog)
            dialog.validate_and_accept()
            return dialog.result()

        with patch.object(orgui.OrganizationTokenDialog, "exec", accept):
            window.configure_organization_tokens()
        self.assertEqual(appmod.get_organization_tokens(), TOKENS)
        self.assertEqual(window.encryption_mode, "organization")
        self.assertTrue(window.organization_mode_action.isChecked())
        self.assertIsNone(dialogs[0].tokens)
        self.assertTrue(all(not field.text() for field in dialogs[0].token_inputs + dialogs[0].check_inputs))
        self.assert_no_errors_or_passwords()

    def test_configure_cancel_or_invalid_check_never_replaces_enrollment(self):
        self.enroll()
        window = self.new_window()
        original = Path(appmod.CONFIG_FILE).read_bytes()
        self.question.return_value = appmod.QMessageBox.StandardButton.Yes
        dialogs = []

        def cancel(dialog):
            dialogs.append(dialog)
            fill_dialog(dialog, OTHER_TOKENS, tuple(map(organization.check_value, OTHER_TOKENS)))
            dialog.reject()
            return dialog.result()

        with patch.object(orgui.OrganizationTokenDialog, "exec", cancel), \
             patch.object(appmod, "save_organization_tokens", wraps=appmod.save_organization_tokens) as save:
            window.configure_organization_tokens()
            save.assert_not_called()
        self.assertEqual(Path(appmod.CONFIG_FILE).read_bytes(), original)
        self.assertTrue(all(not field.text() for field in dialogs[0].token_inputs + dialogs[0].check_inputs))

        def invalid(dialog):
            fill_dialog(dialog, checks=CHECKS[::-1])
            dialog.validate_and_accept()
            return dialog.result()

        with patch.object(orgui.OrganizationTokenDialog, "exec", invalid), \
             patch.object(appmod, "save_organization_tokens", wraps=appmod.save_organization_tokens) as save:
            window.configure_organization_tokens()
            save.assert_not_called()
        self.warning.assert_called_once()
        self.assertEqual(Path(appmod.CONFIG_FILE).read_bytes(), original)
        self.assertEqual(appmod.get_organization_tokens(), TOKENS)

    def test_replacement_and_removal_require_confirmation(self):
        self.enroll()
        window = self.new_window()
        before = Path(appmod.CONFIG_FILE).read_bytes()
        with patch.object(appmod, "OrganizationTokenDialog") as dialog:
            window.configure_organization_tokens()
            dialog.assert_not_called()
        window.forget_organization_tokens()
        self.assertEqual(Path(appmod.CONFIG_FILE).read_bytes(), before)
        self.question.return_value = appmod.QMessageBox.StandardButton.Yes
        window.forget_organization_tokens()
        self.assertNotIn("organization_tokens_protected", appmod.load_config())
        self.assertEqual(window.encryption_mode, "password")
        self.assertTrue(window.password_mode_action.isChecked())
        self.assert_no_errors_or_passwords()

    def test_recovery_preserves_modes_without_embedding_organization_credentials(self):
        self.enroll()
        window = self.new_window()
        org_path, legacy_path = self.root / "org.erica", self.root / "legacy.erica"
        window.current_editor.setPlainText("Organization before recovery")
        self.save_as(window, org_path)
        window.current_editor.setPlainText("Organization recovered edit")
        window.current_editor.document().setModified(True)
        appmod.write_encrypted_document(legacy_path, "<p>Legacy</p>", PASSWORD)
        with patch.object(window, "prompt_password", return_value=PASSWORD):
            window.open_file(str(legacy_path))
        window.current_editor.setPlainText("Legacy recovered edit")
        window.current_editor.document().setModified(True)
        payload = window.build_recovery_payload()
        self.assertEqual([doc["protection_mode"] for doc in payload["documents"]],
                         ["organization", "password"])
        encoded = json.dumps(payload)
        for secret in TOKENS + CHECKS + (PASSWORD,):
            self.assertNotIn(secret, encoded)
        window.autosave_recovery_snapshot()
        recovery = Path(appmod.RECOVERY_FILE).read_bytes()
        restored_payload = json.loads(appmod.decrypt_bytes(recovery, appmod.get_recovery_key()))
        self.assertEqual(restored_payload, payload)
        self.assertNotIn(b"Organization recovered edit", recovery)
        # Restore with a different default: recovered document modes remain pinned.
        window.set_encryption_mode("password")
        self.question.return_value = appmod.QMessageBox.StandardButton.Yes
        window.try_restore_recovery_snapshot()
        self.question.return_value = appmod.QMessageBox.StandardButton.No
        self.assertEqual([doc["protection_mode"] for doc in window.open_documents],
                         ["organization", "password"])
        self.assertEqual([doc["editor"].toPlainText() for doc in window.open_documents],
                         ["Organization recovered edit", "Legacy recovered edit"])
        self.assertTrue(Path(appmod.RECOVERY_FILE).exists())
        self.assertTrue(all(doc["editor"].document().isModified() for doc in window.open_documents))
        # Restoring must not destroy the only copy before a successful save.
        retained_payload = json.loads(appmod.decrypt_bytes(
            Path(appmod.RECOVERY_FILE).read_bytes(), appmod.get_recovery_key()))
        self.assertEqual(retained_payload, payload)
        self.assertTrue(window.silent_save(0))
        with patch.object(window, "prompt_password", return_value=PASSWORD) as prompt:
            self.assertTrue(window.silent_save(1))
            prompt.assert_called_once()
        self.assertTrue(appmod.file_uses_organization(org_path))
        self.assertFalse(appmod.file_uses_organization(legacy_path))
        self.assert_no_errors_or_passwords()


if __name__ == "__main__":
    unittest.main()