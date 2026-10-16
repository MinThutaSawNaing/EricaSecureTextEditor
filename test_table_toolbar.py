"""Offscreen integration tests for the independently constructible table toolbar."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QLabel, QMenu, QSpinBox

import erica_secure_text_editor as appmod
from erica_tables import TableToolbar


class TableToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = appmod.QApplication.instance() or appmod.QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(appmod, "CONFIG_PATH", self.temp.name),
            patch.object(appmod, "CONFIG_FILE", os.path.join(self.temp.name, "config.json")),
            patch.object(appmod, "RECOVERY_FILE", os.path.join(self.temp.name, "recovery.enc")),
        ]
        for p in self.patches:
            p.start()
        self.window = appmod.MainWindow()
        self.toolbar = getattr(self.window, "table_toolbar", None)
        if self.toolbar is None:
            self.toolbar = TableToolbar(self.window)
            self.window.addToolBar(self.toolbar)
        self.editor = self.window.current_editor

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_outside_table_and_sync_never_modifies_document_or_opens_dialog(self):
        self.editor.setPlainText("ordinary text")
        self.editor.document().setModified(False)
        before = self.editor.toHtml()
        with patch.object(self.window, "get_current_table", side_effect=AssertionError), \
             patch.object(QDialog, "exec", side_effect=AssertionError):
            for _ in range(4):
                self.toolbar.sync()
        self.assertEqual(before, self.editor.toHtml())
        self.assertFalse(self.editor.document().isModified())
        self.assertTrue(self.toolbar.insert_action.isEnabled())
        self.assertFalse(self.toolbar.merge_action.isEnabled())
        self.assertFalse(self.toolbar.split_action.isEnabled())
        self.assertTrue(all(not a.isEnabled() for a in self.toolbar.table_actions))
        self.editor.setReadOnly(True)
        self.toolbar.sync()
        self.assertFalse(self.toolbar.insert_action.isEnabled())
        self.toolbar.bind_editor(None)
        self.toolbar.bind_editor(self.editor)

    def test_row_column_actions_delegate_and_resync(self):
        table = self.toolbar.insert_table(3, 3)
        for menu, methods in (
            (self.toolbar.row_menu, ("insert_table_row_above", "insert_table_row_below", "delete_table_row")),
            (self.toolbar.column_menu, ("insert_table_column_left", "insert_table_column_right", "delete_table_column")),
        ):
            for action, method in zip(menu.actions(), methods):
                with self.subTest(method=method), patch.object(self.window, method, wraps=getattr(self.window, method)) as call:
                    action.trigger()
                    call.assert_called_once_with()
                    self.assertIn(f"{table.rows()}×{table.columns()}", self.toolbar.state_label.text())

    def test_delete_table_action_delegates_disables_and_undo_restores(self):
        self.toolbar.insert_table(2, 2)
        self.assertIn(self.toolbar.delete_action, self.toolbar.actions())
        with patch.object(self.window, "delete_current_table", wraps=self.window.delete_current_table) as call:
            self.toolbar.delete_action.trigger()
            call.assert_called_once_with()
        self.assertEqual(self.editor.document().rootFrame().childFrames(), [])
        self.assertFalse(self.toolbar.delete_action.isEnabled())
        self.editor.undo()
        self.assertEqual(len(self.editor.document().rootFrame().childFrames()), 1)

    def test_encrypted_html_roundtrip_plain_removes_recognized_styles(self):
        for style, row, background, foreground in (
            ("Blue header", 0, "#245a81", "#ffffff"),
            ("Banded rows", 1, "#eaf2f8", "#202124"),
        ):
            with self.subTest(style=style):
                self.editor.clear()
                table = self.toolbar.insert_table(3, 2)
                cursor = table.cellAt(row, 0).firstCursorPosition()
                fmt = QTextCharFormat()
                fmt.setFontItalic(True)
                fmt.setFontFamily("Courier New")
                fmt.setFontPointSize(15)
                cursor.insertText("Keep my font", fmt)
                self.toolbar.apply_style(style)
                encrypted = appmod.encrypt_text(self.editor.toHtml(), "Table-roundtrip-123!")
                self.editor.setHtml(appmod.decrypt_text(encrypted, "Table-roundtrip-123!"))
                table = self.editor.document().rootFrame().childFrames()[0]
                cell = table.cellAt(row, 0)
                self.assertEqual(cell.format().background().color(), QColor(background))
                cursor = cell.firstCursorPosition()
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                self.assertEqual(cursor.charFormat().foreground().color(), QColor(foreground))
                self.editor.setTextCursor(cursor)
                before = self.editor.toHtml()
                self.toolbar.apply_style("Plain")
                self.assertNotEqual(cell.format().background().color(), QColor(background))
                char = cursor.charFormat()
                self.assertNotEqual(char.foreground().color(), QColor(foreground))
                self.assertTrue(char.fontItalic())
                self.assertEqual(char.fontPointSize(), 15)
                self.assertIn("Courier New", char.fontFamilies())
                if style == "Blue header":
                    self.assertLess(char.fontWeight(), int(QFont.Weight.Bold))
                self.editor.undo()
                self.assertEqual(before, self.editor.toHtml())

    def test_combined_insert_dialog_defaults_preview_accept_and_undo(self):
        def accept(dialog):
            rows = dialog.findChild(QSpinBox, "rows")
            cols = dialog.findChild(QSpinBox, "columns")
            self.assertEqual((rows.value(), cols.value()), (3, 3))
            self.assertEqual((rows.minimum(), rows.maximum()), (1, 50))
            self.assertEqual((cols.minimum(), cols.maximum()), (1, 50))
            rows.setValue(2)
            cols.setValue(4)
            dialog.findChild(QCheckBox, "header").setChecked(True)
            dialog.findChild(QComboBox, "style").setCurrentText("Blue header")
            self.assertIn("2 rows × 4 columns", dialog.findChild(QLabel, "preview").text())
            self.assertIn("Blue", dialog.findChild(QLabel, "preview").text())
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, "exec", accept):
            self.toolbar.insert_action.trigger()
        table = self.editor.textCursor().currentTable()
        self.assertEqual((table.rows(), table.columns()), (2, 4))
        self.assertEqual(table.format().headerRowCount(), 1)
        self.assertEqual(table.cellAt(0, 0).format().background().color(), QColor("#245a81"))
        self.editor.undo()
        self.assertEqual(self.editor.document().rootFrame().childFrames(), [])
        self.assertFalse(self.toolbar.merge_action.isEnabled())

    def test_properties_dialog_roundtrip_and_single_undo(self):
        table = self.toolbar.insert_table(3, 3)
        before = self.editor.toHtml()
        def accept(dialog):
            self.assertEqual(dialog.findChild(QSpinBox, "padding").value(), 6)
            dialog.findChild(QSpinBox, "border").setValue(3)
            dialog.findChild(QSpinBox, "padding").setValue(10)
            dialog.findChild(QSpinBox, "width").setValue(65)
            dialog.findChild(QCheckBox, "header").setChecked(True)
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, "exec", accept):
            self.toolbar.table_properties_dialog()
        fmt = table.format()
        self.assertEqual((fmt.border(), fmt.cellPadding(), fmt.width().rawValue(), fmt.headerRowCount()),
                         (3, 10, 65, 1))
        def cancel(dialog):
            self.assertEqual(dialog.findChild(QSpinBox, "width").value(), 65)
            self.assertTrue(dialog.findChild(QCheckBox, "header").isChecked())
            return QDialog.DialogCode.Rejected
        after = self.editor.toHtml()
        with patch.object(QDialog, "exec", cancel):
            self.toolbar.table_properties_dialog()
        self.assertEqual(after, self.editor.toHtml())
        self.editor.undo()
        self.assertEqual(before, self.editor.toHtml())

    def test_style_preserves_content_selection_fonts_and_plain_restores_colours(self):
        table = self.toolbar.insert_table(3, 3)
        cursor = table.cellAt(0, 0).firstCursorPosition()
        fmt = QTextCharFormat()
        fmt.setFontItalic(True)
        fmt.setFontFamily("Courier New")
        fmt.setForeground(QColor("#8a1234"))
        cursor.insertText("Header", fmt)
        cursor = table.cellAt(1, 0).firstCursorPosition()
        cursor.insertText("Body")
        self.toolbar.select("Table")
        selection = self.editor.textCursor()
        positions = (selection.anchor(), selection.position())
        before = self.editor.toHtml()
        self.toolbar.apply_style("Blue header")
        self.assertEqual(positions, (self.editor.textCursor().anchor(), self.editor.textCursor().position()))
        self.assertIn("Header", self.editor.toPlainText())
        styled = table.cellAt(0, 0).firstCursorPosition()
        styled.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
        self.assertTrue(styled.charFormat().fontItalic())
        self.assertEqual(styled.charFormat().foreground().color(), QColor("white"))
        self.editor.undo()
        self.assertEqual(before, self.editor.toHtml())
        self.toolbar.apply_style("Blue header")
        self.toolbar.apply_style("Banded rows")
        self.assertEqual(table.cellAt(1, 0).format().background().color(), QColor("#eaf2f8"))
        self.toolbar.apply_style("Plain")
        self.assertEqual(before, self.editor.toHtml())

    def test_select_merge_split_states_and_unique_merged_cells(self):
        table = self.toolbar.insert_table(3, 3)
        self.assertFalse(self.toolbar.merge_action.isEnabled())
        self.assertFalse(self.toolbar.split_action.isEnabled())
        self.toolbar.select("Row")
        self.assertEqual(self.editor.textCursor().selectedTableCells(), (0, 1, 0, 3))
        self.assertTrue(self.toolbar.merge_action.isEnabled())
        self.toolbar.merge_action.trigger()
        self.assertEqual(table.cellAt(0, 0).columnSpan(), 3)
        self.assertTrue(self.toolbar.split_action.isEnabled())
        self.assertEqual(len(list(self.toolbar._cells(table))), 7)
        self.toolbar.apply_style("Blue header")
        self.toolbar.split_action.trigger()
        self.assertEqual(table.cellAt(0, 0).columnSpan(), 1)
        self.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.toolbar.select("Column")
        self.assertEqual(self.editor.textCursor().selectedTableCells(), (0, 3, 0, 1))
        self.toolbar.select("Table")
        self.assertEqual(self.editor.textCursor().selectedTableCells(), (0, 3, 0, 3))

    def test_resize_single_undo_and_constraints_use_fresh_column_count(self):
        table = self.toolbar.insert_table(2, 2)
        self.toolbar.set_table_properties(2, 8, 55, False)
        before = self.editor.toHtml()
        self.toolbar.fit_width()
        self.assertEqual(table.format().width().rawValue(), 100)
        self.editor.undo()
        self.assertEqual(before, self.editor.toHtml())
        self.window.insert_table_column_right()
        before_equal = self.editor.toHtml()
        self.toolbar.equal_columns()
        constraints = table.format().columnWidthConstraints()
        self.assertEqual(len(constraints), 3)
        self.assertTrue(all(abs(c.rawValue() - 100/3) < .001 for c in constraints))
        self.editor.undo()
        self.assertEqual(before_equal, self.editor.toHtml())
        self.editor.document().setModified(False)
        before_sync = self.editor.toHtml()
        selection = self.editor.textCursor()
        with patch.object(QDialog, "exec", side_effect=AssertionError):
            self.toolbar.sync()
        self.assertEqual(before_sync, self.editor.toHtml())
        self.assertFalse(self.editor.document().isModified())
        self.assertEqual((selection.anchor(), selection.position()),
                         (self.editor.textCursor().anchor(), self.editor.textCursor().position()))

    def test_clean_window_and_context_controls_outside_table(self):
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.window.font_toolbar.isVisible())
        self.assertFalse(self.toolbar.isVisible())
        self.assertEqual(self.window.toolBarArea(self.toolbar), appmod.Qt.ToolBarArea.NoToolBarArea)
        self.editor.setPlainText("Select me")
        self.editor.selectAll()
        before = self.editor.toHtml()
        self.editor.document().setModified(False)
        point = self.editor.cursorRect().center()
        def capture(menu, position):
            self.assertEqual([a.text() for a in menu.actions() if a.menu()],
                             ["Font", "Paragraph", "Table"])
            font = next(a.menu() for a in menu.actions() if a.text() == "Font")
            self.assertTrue(all(label in [a.text() for a in font.actions()] for label in
                                ["Choose font…", "Font size…", "Bold", "Italic", "Underline",
                                 "Strikethrough", "Text color", "Highlight"]))
            table = next(a.menu() for a in menu.actions() if a.text() == "Table")
            self.assertEqual([a.text() for a in table.actions()], ["Insert table"])
            self.assertTrue(table.actions()[0].isEnabled())
        with patch.object(QMenu, "exec", capture):
            self.toolbar.show_context_menu(self.editor, point)
        self.assertEqual(before, self.editor.toHtml())
        self.assertFalse(self.editor.document().isModified())
        self.assertEqual(self.editor.textCursor().selectedText(), "Select me")

    def test_context_menu_rectangular_selection_uses_cell_bounds(self):
        self.window.show()
        table = self.toolbar.insert_table(3, 3)
        self.editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self.toolbar.select("Column")
        self.app.processEvents()
        self.assertEqual(self.editor.textCursor().selectedTableCells(), (0, 3, 0, 1))
        before = self.editor.textCursor()
        inside = self.editor.cursorRect(table.cellAt(1, 0).firstCursorPosition()).center()
        outside = self.editor.cursorRect(table.cellAt(1, 2).firstCursorPosition()).center()
        clicked = self.editor.cursorForPosition(outside)
        self.assertTrue(before.selectionStart() < clicked.position() < before.selectionEnd())
        with patch.object(QMenu, "exec", return_value=None):
            self.toolbar.show_context_menu(self.editor, inside)
        self.assertEqual((before.anchor(), before.position()),
                         (self.editor.textCursor().anchor(), self.editor.textCursor().position()))
        with patch.object(QMenu, "exec", return_value=None):
            self.toolbar.show_context_menu(self.editor, outside)
        self.assertFalse(self.editor.textCursor().hasSelection())
        cell = table.cellAt(self.editor.textCursor())
        self.assertEqual((cell.row(), cell.column()), (1, 2))

    def test_context_menu_retains_default_actions_and_selection_without_clipboard_changes(self):
        self.window.show()
        table = self.toolbar.insert_table(3, 3)
        table.cellAt(0, 0).firstCursorPosition().insertText("first")
        self.toolbar.select("Table")
        self.app.processEvents()
        before = self.editor.textCursor()
        point = self.editor.cursorRect(table.cellAt(1, 1).firstCursorPosition()).center()
        appmod.QApplication.clipboard().setText("untouched")
        seen = []
        def capture(menu, position):
            def collect(parent):
                for action in parent.actions():
                    seen.append(action.text())
                    if action.menu():
                        collect(action.menu())
            collect(menu)
        with patch.object(QMenu, "exec", capture):
            self.toolbar.show_context_menu(self.editor, point)
        self.assertEqual((before.anchor(), before.position()),
                         (self.editor.textCursor().anchor(), self.editor.textCursor().position()))
        self.assertIn("Row", seen)
        self.assertIn("Delete table", seen)
        self.assertTrue(any("Copy" in label for label in seen))
        self.assertEqual(appmod.QApplication.clipboard().text(), "untouched")
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText("\nOutside table")
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        point = self.editor.cursorRect().center()
        seen.clear()
        with patch.object(QMenu, "exec", capture):
            self.toolbar.show_context_menu(self.editor, point)
        self.assertNotIn("Row", seen)


if __name__ == "__main__":
    unittest.main()