"""Standalone toolbar regressions; no MainWindow integration is required."""

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit

from erica_formatting import FontToolbar


class FontToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QMainWindow()
        self.editor = QTextEdit(self.window)
        self.window.current_editor = self.editor
        self.window.apply_bullet_list = Mock()
        self.window.apply_numbered_list = Mock()
        self.toolbar = FontToolbar(self.window)
        self.editor.setPlainText("alpha beta")
        self.editor.document().setModified(False)

    def tearDown(self):
        self.toolbar.bind_editor(None)
        self.window.close()
        self.window.deleteLater()

    def test_context_font_dialog_preserves_mixed_styles_and_cancel_is_noop(self):
        self.select(0, 2)
        self.toolbar.toggle_italic()
        self.select(0, 5)
        before = self.editor.toHtml()
        initial = self.editor.currentFont()
        with patch('erica_formatting.QFontDialog.getFont', return_value=(initial, False)):
            self.toolbar.choose_font()
        self.assertEqual(before, self.editor.toHtml())
        chosen = QFont(initial)
        chosen.setPointSizeF(24)
        with patch('erica_formatting.QFontDialog.getFont', return_value=(chosen, True)):
            self.toolbar.choose_font()
        self.assertEqual(self.char_format(0).fontPointSize(), 24)
        self.assertTrue(self.char_format(0).fontItalic())
        self.assertFalse(self.char_format(3).fontItalic())
        self.assertEqual(self.editor.textCursor().selectedText(), "alpha")

    def test_context_size_dialog_accept_and_cancel(self):
        self.select(0, 5)
        before = self.editor.toHtml()
        with patch('erica_formatting.QInputDialog.getDouble', return_value=(32, False)):
            self.toolbar.choose_font_size()
        self.assertEqual(before, self.editor.toHtml())
        with patch('erica_formatting.QInputDialog.getDouble', return_value=(18.5, True)):
            self.toolbar.choose_font_size()
        self.assertEqual(self.char_format(0).fontPointSize(), 18.5)
        self.editor.undo()
        self.assertEqual(before, self.editor.toHtml())

    def select(self, start, end):
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def char_format(self, position):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,
                            QTextCursor.MoveMode.KeepAnchor)
        return cursor.charFormat()

    def test_minimal_merge_preserves_mixed_formatting_and_selection(self):
        self.select(0, 2)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("red"))
        fmt.setFontItalic(True)
        self.editor.mergeCurrentCharFormat(fmt)
        self.select(2, 5)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("blue"))
        self.editor.mergeCurrentCharFormat(fmt)
        self.select(5, 0)  # Retain backwards selections as well.
        self.toolbar.toggle_bold()
        self.toolbar.set_font_size(18.5)
        self.toolbar.set_font_family("Arial")
        cursor = self.editor.textCursor()
        self.assertEqual((cursor.anchor(), cursor.position()), (5, 0))
        self.assertEqual(self.char_format(0).foreground().color(), QColor("red"))
        self.assertTrue(self.char_format(0).fontItalic())
        self.assertEqual(self.char_format(3).foreground().color(), QColor("blue"))
        self.assertFalse(self.char_format(3).fontItalic())
        self.assertEqual(self.char_format(3).fontPointSize(), 18.5)
        self.assertEqual(self.char_format(3).fontWeight(), QFont.Weight.Bold)
        self.assertNotEqual(self.char_format(7).fontWeight(), QFont.Weight.Bold)

    def test_no_selection_affects_next_typing_only(self):
        self.select(5, 5)
        before = self.editor.toHtml()
        self.toolbar.toggle_bold()
        self.toolbar.toggle_italic()
        self.toolbar.toggle_underline()
        self.toolbar.toggle_strikethrough()
        self.toolbar.set_font_size(22)
        self.assertEqual(self.editor.toHtml(), before)
        self.assertFalse(self.editor.document().isModified())
        self.editor.insertPlainText("X")
        fmt = self.char_format(5)
        self.assertEqual(fmt.fontWeight(), QFont.Weight.Bold)
        self.assertTrue(fmt.fontItalic())
        self.assertTrue(fmt.fontUnderline())
        self.assertTrue(fmt.fontStrikeOut())
        self.assertEqual(fmt.fontPointSize(), 22)
        self.assertNotEqual(self.char_format(0).fontWeight(), QFont.Weight.Bold)

    def test_sync_and_programmatic_controls_do_not_modify_document(self):
        self.select(0, 5)
        before = self.editor.toHtml()
        revision = self.editor.document().revision()
        for _ in range(3):
            self.toolbar.sync()
        self.toolbar.font_combo.setCurrentFont(QFont("Arial"))
        self.toolbar.size_spin.setValue(36)
        self.toolbar.size_spin.editingFinished.emit()  # Mere focus loss is not an edit.
        self.assertEqual(self.editor.toHtml(), before)
        self.assertEqual(self.editor.document().revision(), revision)
        self.assertFalse(self.editor.document().isModified())
        self.assertFalse(self.editor.document().isUndoAvailable())

    def test_user_size_step_and_family_activation(self):
        self.select(0, 5)
        self.toolbar.size_spin.setValue(12)
        self.toolbar.size_spin.stepUp()
        self.assertEqual(self.char_format(0).fontPointSize(), 12.5)
        self.toolbar.font_combo.setCurrentFont(QFont("Arial"))
        family = self.toolbar.font_combo.currentFont().family()
        self.toolbar.font_combo.activated.emit(self.toolbar.font_combo.currentIndex())
        self.assertEqual(self.char_format(0).fontFamilies(), [family])

    def test_tab_switch_disconnects_old_signals_and_targets_new_editor(self):
        old = self.editor
        second = QTextEdit(self.window)
        second.setPlainText("second")
        self.window.current_editor = second
        self.toolbar.bind_editor(second)
        with patch.object(self.toolbar, "sync", wraps=self.toolbar.sync) as sync:
            old.setFontItalic(True)
            self.assertEqual(sync.call_count, 0)
        self.toolbar.toggle_underline()
        self.assertTrue(second.currentCharFormat().fontUnderline())
        self.assertFalse(old.currentCharFormat().fontUnderline())
        self.toolbar.bind_editor(second)
        self.assertEqual(len(self.toolbar._connections), 5)
        self.toolbar.bind_editor(None)
        self.assertFalse(self.toolbar.isEnabled())
        self.toolbar.toggle_bold()
        self.toolbar.undo()

    def test_can_construct_before_first_editor(self):
        self.window.current_editor = None
        toolbar = FontToolbar(self.window)
        self.assertFalse(toolbar.isEnabled())
        toolbar.bind_editor(self.editor)
        self.assertTrue(toolbar.isEnabled())
        toolbar.bind_editor(None)

    def test_missing_font_displays_requested_family_without_modification(self):
        missing = "Erica Regression Font Not Installed 93471"
        self.select(0, 5)
        self.toolbar.set_font_family(missing)
        before = self.editor.toHtml()
        self.editor.document().setModified(False)
        self.toolbar.sync()
        self.assertEqual(self.toolbar.font_combo.currentText(), missing)
        self.assertEqual(self.editor.toHtml(), before)
        self.assertFalse(self.editor.document().isModified())

    def test_readonly_disables_controls_and_all_direct_edit_commands(self):
        self.select(0, 5)
        self.toolbar.toggle_bold()  # Ensure undo history exists.
        self.editor.setReadOnly(True)
        self.toolbar.sync()
        self.assertFalse(self.toolbar.isEnabled())
        self.assertFalse(self.toolbar.font_combo.isEnabled())
        self.assertFalse(self.toolbar.size_spin.isEnabled())
        self.assertFalse(self.toolbar.undo_action.isEnabled())
        before = self.editor.toHtml()
        revision = self.editor.document().revision()
        current = self.editor.currentCharFormat()
        fmt = QTextCharFormat()
        fmt.setFontItalic(True)
        with patch("erica_formatting.QColorDialog.getColor") as dialog:
            for command in (
                self.toolbar.toggle_bold, self.toolbar.toggle_italic,
                self.toolbar.toggle_underline, self.toolbar.toggle_strikethrough,
                self.toolbar.increase_font_size, self.toolbar.decrease_font_size,
                self.toolbar.choose_foreground, self.toolbar.choose_highlight,
                self.toolbar.undo, self.toolbar.redo,
                lambda: self.toolbar.set_font_family("Arial"),
                lambda: self.toolbar.set_font_size(24),
                lambda: self.toolbar.apply_char_format(fmt),
                lambda: self.toolbar.set_alignment(Qt.AlignmentFlag.AlignRight),
                lambda: self.toolbar._window_command("apply_bullet_list"),
                lambda: self.toolbar._window_command("apply_numbered_list"),
            ):
                command()
            dialog.assert_not_called()
        self.assertEqual(self.editor.toHtml(), before)
        self.assertEqual(self.editor.currentCharFormat(), current)
        self.assertEqual(self.editor.document().revision(), revision)
        self.window.apply_bullet_list.assert_not_called()
        self.window.apply_numbered_list.assert_not_called()
        self.editor.setReadOnly(False)
        self.toolbar.sync()
        self.assertTrue(self.toolbar.isEnabled())
        self.assertTrue(self.toolbar.undo_action.isEnabled())

    def test_formatting_undo_redo(self):
        self.select(0, 5)
        before = self.editor.toHtml()
        self.toolbar.bold_action.trigger()
        after = self.editor.toHtml()
        self.assertNotEqual(before, after)
        self.assertTrue(self.toolbar.undo_action.isEnabled())
        self.toolbar.undo_action.trigger()
        self.assertEqual(self.editor.toHtml(), before)
        self.assertTrue(self.toolbar.redo_action.isEnabled())
        self.toolbar.redo_action.trigger()
        self.assertEqual(self.editor.toHtml(), after)

    def test_color_cancel_and_minimal_color_merge(self):
        self.select(0, 5)
        self.toolbar.toggle_italic()
        before = self.editor.toHtml()
        with patch("erica_formatting.QColorDialog.getColor", return_value=QColor()):
            self.toolbar.choose_foreground()
            self.toolbar.choose_highlight()
        self.assertEqual(self.editor.toHtml(), before)
        with patch("erica_formatting.QColorDialog.getColor", return_value=QColor("yellow")):
            self.toolbar.choose_highlight()
        self.assertTrue(self.char_format(0).fontItalic())
        self.assertEqual(self.char_format(0).background().color(), QColor("yellow"))

    def test_alignment_lists_and_size_validation(self):
        self.toolbar.set_alignment(Qt.AlignmentFlag.AlignRight)
        self.assertTrue(self.editor.alignment() & Qt.AlignmentFlag.AlignRight)
        self.toolbar.bullet_action.trigger()
        self.toolbar.number_action.trigger()
        self.window.apply_bullet_list.assert_called_once_with()
        self.window.apply_numbered_list.assert_called_once_with()
        self.select(0, 5)
        before = self.editor.toHtml()
        for invalid in (0, 201, "bad", None, float("nan"), float("inf")):
            self.toolbar.set_font_size(invalid)
        self.assertEqual(self.editor.toHtml(), before)
        self.toolbar.set_font_size(200)
        self.toolbar.increase_font_size()
        self.assertEqual(self.char_format(0).fontPointSize(), 200)
        self.toolbar.set_font_size(1)
        self.toolbar.decrease_font_size()
        self.assertEqual(self.char_format(0).fontPointSize(), 1)


if __name__ == "__main__":
    unittest.main()