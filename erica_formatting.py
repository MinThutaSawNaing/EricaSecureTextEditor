"""Native formatting controls, independent of the application's document lifecycle.

Call ``bind_editor(window.current_editor)`` after each tab change (None is valid).
Menu commands may delegate to the public formatting methods on this toolbar.
"""

import math

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QFont, QTextCharFormat
from PyQt6.QtWidgets import (
    QColorDialog, QDoubleSpinBox, QFontComboBox, QFontDialog, QHBoxLayout, QInputDialog, QLabel,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)


class _FontSize(QDoubleSpinBox):
    """Emit only for user commits/steps, not programmatic value changes."""

    activated = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(1, 200)
        self.setDecimals(1)
        self.setSingleStep(0.5)
        self.setKeyboardTracking(False)
        self._edited = False
        self.lineEdit().textEdited.connect(self._mark_edited)
        self.editingFinished.connect(self._commit)

    def _mark_edited(self, _text):
        self._edited = True

    def _commit(self):
        if self._edited:
            self._edited = False
            self.activated.emit(self.value())

    def stepBy(self, steps):
        super().stepBy(steps)
        self._edited = False
        self.activated.emit(self.value())


class FontToolbar(QToolBar):
    """Two compact rows of native font, paragraph and history controls."""

    def __init__(self, window):
        super().__init__("Text formatting", window)
        self.setObjectName("fontToolbar")
        self.setAccessibleName("Text formatting")
        self.window = window
        self.editor = None
        self._connections = []
        panel = QWidget(self)
        rows = QVBoxLayout(panel)
        rows.setContentsMargins(4, 2, 4, 2)
        rows.setSpacing(2)
        font_row, paragraph_row = QHBoxLayout(), QHBoxLayout()
        rows.addLayout(font_row)
        rows.addLayout(paragraph_row)
        self.addWidget(panel)

        self.font_combo = QFontComboBox(panel)
        self.font_combo.setAccessibleName("Font family")
        self.font_combo.setToolTip("Font family")
        self.font_combo.setMinimumWidth(160)
        label = QLabel("Font:", panel)
        label.setBuddy(self.font_combo)
        font_row.addWidget(label)
        font_row.addWidget(self.font_combo)
        # activated, unlike currentFontChanged, never fires during synchronization.
        self.font_combo.activated.connect(
            lambda _index: self.set_font_family(self.font_combo.currentFont().family()))
        self.size_spin = _FontSize(panel)
        self.size_spin.setAccessibleName("Font size")
        self.size_spin.setToolTip("Font size in points (1–200)")
        label = QLabel("Size:", panel)
        label.setBuddy(self.size_spin)
        font_row.addWidget(label)
        font_row.addWidget(self.size_spin)
        self.size_spin.activated.connect(self.set_font_size)

        self.bold_action = self._action(font_row, "Bold", self.toggle_bold, True)
        self.italic_action = self._action(font_row, "Italic", self.toggle_italic, True)
        self.underline_action = self._action(font_row, "Underline", self.toggle_underline, True)
        self.strikethrough_action = self._action(
            font_row, "Strikethrough", self.toggle_strikethrough, True)
        self.foreground_action = self._action(font_row, "Text color", self.choose_foreground)
        self.highlight_action = self._action(font_row, "Highlight", self.choose_highlight)
        font_row.addStretch()

        self.alignment_actions = {}
        self.alignment_group = QActionGroup(self)
        for text, alignment in (
            ("Align left", Qt.AlignmentFlag.AlignLeft),
            ("Center", Qt.AlignmentFlag.AlignHCenter),
            ("Align right", Qt.AlignmentFlag.AlignRight),
            ("Justify", Qt.AlignmentFlag.AlignJustify),
        ):
            action = self._action(paragraph_row, text,
                                  lambda a=alignment: self.set_alignment(a), True)
            self.alignment_group.addAction(action)
            self.alignment_actions[alignment] = action
        self.bullet_action = self._action(
            paragraph_row, "Bullets", lambda: self._window_command("apply_bullet_list"))
        self.number_action = self._action(
            paragraph_row, "Numbering", lambda: self._window_command("apply_numbered_list"))
        self.undo_action = self._action(paragraph_row, "Undo", self.undo)
        self.redo_action = self._action(paragraph_row, "Redo", self.redo)
        paragraph_row.addStretch()
        self.bind_editor(getattr(window, "current_editor", None))

    def _action(self, row, text, callback, checkable=False):
        action = QAction(text, self)
        action.setToolTip(text)
        action.setCheckable(checkable)
        action.triggered.connect(lambda _checked=False: callback())
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setAccessibleName(text)
        row.addWidget(button)
        return action

    def bind_editor(self, editor):
        """Disconnect all old editor signals before observing the new editor."""
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass  # The previous tab may already have been deleted.
        self._connections.clear()
        self.editor = editor
        if editor is not None:
            for signal in (editor.currentCharFormatChanged, editor.cursorPositionChanged,
                           editor.selectionChanged, editor.undoAvailable, editor.redoAvailable):
                slot = lambda *_args: self.sync()
                signal.connect(slot)
                self._connections.append((signal, slot))
        self.sync()

    def sync(self):
        """Read editor state only; never write a document while updating controls."""
        editor = self.editor
        self.setEnabled(self._can_edit())
        if editor is None:
            return
        controls = [self.font_combo, self.size_spin, self.bold_action,
                    self.italic_action, self.underline_action, self.strikethrough_action,
                    *self.alignment_actions.values()]
        blockers = [QSignalBlocker(control) for control in controls]
        try:
            fmt = editor.currentCharFormat()
            self.font_combo.setCurrentFont(editor.currentFont())
            # QFontComboBox may select an unrelated installed family when the
            # requested document font is missing. Keep the requested name visible;
            # Qt still handles actual glyph fallback without rewriting the document.
            self.font_combo.setEditText(editor.currentFont().family())
            size = fmt.fontPointSize() or editor.currentFont().pointSizeF()
            if size <= 0:
                size = editor.document().defaultFont().pointSizeF()
            self.size_spin.setValue(size if size > 0 else 12)
            self.size_spin._edited = False
            self.bold_action.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
            self.italic_action.setChecked(fmt.fontItalic())
            self.underline_action.setChecked(fmt.fontUnderline())
            self.strikethrough_action.setChecked(fmt.fontStrikeOut())
            alignment = editor.alignment()
            for flag, action in self.alignment_actions.items():
                action.setChecked(bool(alignment & flag))
            self.undo_action.setEnabled(self._can_edit() and editor.document().isUndoAvailable())
            self.redo_action.setEnabled(self._can_edit() and editor.document().isRedoAvailable())
        finally:
            del blockers

    def _can_edit(self):
        return self.editor is not None and not self.editor.isReadOnly()

    def populate_context_menu(self, menu):
        """Reuse formatting commands without showing permanent toolbar controls."""
        self.sync()
        font_menu = menu.addMenu("Font")
        font_menu.setEnabled(self._can_edit())
        font_menu.addAction("Choose font…", self.choose_font)
        font_menu.addAction("Font size…", self.choose_font_size)
        font_menu.addSeparator()
        for action in (self.bold_action, self.italic_action, self.underline_action,
                       self.strikethrough_action):
            font_menu.addAction(action)
        font_menu.addSeparator()
        font_menu.addAction(self.foreground_action)
        font_menu.addAction(self.highlight_action)
        paragraph_menu = menu.addMenu("Paragraph")
        paragraph_menu.setEnabled(self._can_edit())
        for action in self.alignment_actions.values():
            paragraph_menu.addAction(action)
        paragraph_menu.addSeparator()
        paragraph_menu.addAction(self.bullet_action)
        paragraph_menu.addAction(self.number_action)

    def choose_font(self):
        if not self._can_edit():
            return
        initial = self.editor.currentFont()
        font, accepted = QFontDialog.getFont(initial, self.window, "Choose font")
        if not accepted:
            return
        # Only merge properties the user changed, preserving mixed formatting.
        fmt = QTextCharFormat()
        for getter, setter in (("family", "setFontFamilies"),
                               ("pointSizeF", "setFontPointSize"),
                               ("weight", "setFontWeight"),
                               ("italic", "setFontItalic"),
                               ("underline", "setFontUnderline"),
                               ("strikeOut", "setFontStrikeOut")):
            value = getattr(font, getter)()
            if value != getattr(initial, getter)():
                getattr(fmt, setter)([value] if getter == "family" else value)
        if not fmt.isEmpty():
            self.apply_char_format(fmt)

    def choose_font_size(self):
        if not self._can_edit():
            return
        self.sync()
        value, accepted = QInputDialog.getDouble(
            self.window, "Font size", "Size in points:", self.size_spin.value(), 1, 200, 1)
        if accepted:
            self.set_font_size(value)

    def apply_char_format(self, char_format):
        """Merge only specified properties; an empty selection affects next typing."""
        if self._can_edit():
            self.editor.mergeCurrentCharFormat(char_format)
            self.editor.setFocus()
            self.sync()

    def set_font_family(self, name):
        if not isinstance(name, str) or not name.strip():
            return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([name.strip()])
        self.apply_char_format(fmt)

    def set_font_size(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value) or not 1 <= value <= 200:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(value)
        self.apply_char_format(fmt)

    def increase_font_size(self):
        self.set_font_size(min(200, self.size_spin.value() + 0.5))

    def decrease_font_size(self):
        self.set_font_size(max(1, self.size_spin.value() - 0.5))

    def _toggle(self, getter, setter):
        if self.editor is None:
            return
        fmt = QTextCharFormat()
        getattr(fmt, setter)(not getattr(self.editor.currentCharFormat(), getter)())
        self.apply_char_format(fmt)

    def toggle_bold(self):
        if self.editor is not None:
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Normal if self.editor.currentCharFormat().fontWeight()
                              >= QFont.Weight.Bold else QFont.Weight.Bold)
            self.apply_char_format(fmt)

    def toggle_italic(self):
        self._toggle("fontItalic", "setFontItalic")

    def toggle_underline(self):
        self._toggle("fontUnderline", "setFontUnderline")

    def toggle_strikethrough(self):
        self._toggle("fontStrikeOut", "setFontStrikeOut")

    def _choose_color(self, background=False):
        if not self._can_edit():
            return
        current = self.editor.currentCharFormat()
        initial = current.background().color() if background else current.foreground().color()
        color = QColorDialog.getColor(initial, self, "Highlight color" if background else "Text color")
        if color.isValid():
            fmt = QTextCharFormat()
            (fmt.setBackground if background else fmt.setForeground)(color)
            self.apply_char_format(fmt)

    def choose_foreground(self):
        self._choose_color()

    def choose_highlight(self):
        self._choose_color(True)

    def set_alignment(self, alignment):
        if self._can_edit():
            self.editor.setAlignment(alignment)
            self.editor.setFocus()
            self.sync()

    def _window_command(self, name):
        if self._can_edit():
            getattr(self.window, name)()
            self.sync()

    def undo(self):
        if self._can_edit():
            self.editor.undo()
            self.sync()

    def redo(self):
        if self._can_edit():
            self.editor.redo()
            self.sync()