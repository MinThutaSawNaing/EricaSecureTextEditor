"""Native table controls, independent of MainWindow's legacy table commands."""
from contextlib import contextmanager

from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QTextCursor, QTextFormat, QTextLength, QTextTableFormat
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QMenu, QSpinBox, QToolBar, QToolButton,
)


STYLES = ("Plain", "Blue header", "Banded rows")
_STYLE_ORIGINAL = QTextFormat.Property.UserProperty + 831


def _restore(fmt):
    # Keep saved values in native QVariant properties. PyQt's setProperty
    # overload for dict/list values is ambiguous with QTextLength sequences.
    saved = fmt.property(_STYLE_ORIGINAL)
    if isinstance(saved, str) and saved:
        for key in saved.split(","):
            prop = int(key)
            storage = _STYLE_ORIGINAL + 1 + prop
            if not fmt.hasProperty(storage):
                fmt.clearProperty(prop)
            else:
                fmt.setProperty(prop, fmt.property(storage))
                fmt.clearProperty(storage)
        fmt.clearProperty(_STYLE_ORIGINAL)
    return fmt


def _decorate(fmt, changes):
    fmt = _restore(fmt)
    if changes:
        fmt.setProperty(_STYLE_ORIGINAL, ",".join(str(int(prop)) for prop in changes))
        for prop, value in changes.items():
            if fmt.hasProperty(prop):
                fmt.setProperty(_STYLE_ORIGINAL + 1 + int(prop), fmt.property(prop))
            fmt.setProperty(prop, value)
    return fmt


def _clear_serialized_style(fmt, kind):
    """HTML loses our undoable original-format metadata.

    Recognize only our palette in styled cells on reload. Original pre-save
    colours/weight cannot be recovered, but unrelated font properties survive.
    Live formats with metadata always use exact restoration instead.
    """
    if fmt.hasProperty(_STYLE_ORIGINAL) or not kind:
        return fmt
    prop = QTextFormat.Property
    if fmt.background().color().name() in ("#245a81", "#eaf2f8"):
        fmt.clearProperty(prop.BackgroundBrush)
    expected = "#ffffff" if kind == "header" else "#202124"
    if fmt.foreground().color().name() == expected:
        fmt.clearProperty(prop.ForegroundBrush)
    if kind == "header" and fmt.fontWeight() == int(QFont.Weight.Bold):
        fmt.clearProperty(prop.FontWeight)
    return fmt


class TableToolbar(QToolBar):
    def __init__(self, window):
        super().__init__("Tables", window)
        self.window = window
        self.editor = None
        self.setObjectName("tableToolbar")
        self.table_actions = []
        self.insert_action = self.addAction("Insert table", self.insert_table_dialog)
        self.row_menu = self._menu("Row")
        self.column_menu = self._menu("Column")
        for label, method in (("Above", "insert_table_row_above"),
                              ("Below", "insert_table_row_below"),
                              ("Delete row", "delete_table_row")):
            self._delegate(self.row_menu, label, method)
        for label, method in (("Left", "insert_table_column_left"),
                              ("Right", "insert_table_column_right"),
                              ("Delete column", "delete_table_column")):
            self._delegate(self.column_menu, label, method)
        self.merge_action = self._delegate(self, "Merge", "merge_selected_table_cells")
        self.split_action = self._delegate(self, "Split", "split_current_table_cell")
        self.delete_action = self._delegate(self, "Delete table", "delete_current_table")
        self.appearance_menu = self._menu("Appearance")
        for style in STYLES:
            self._action(self.appearance_menu, style, lambda s=style: self.apply_style(s))
        self.appearance_menu.addSeparator()
        self._action(self.appearance_menu, "Fit width", self.fit_width)
        self._action(self.appearance_menu, "Equal columns", self.equal_columns)
        self._delegate(self.appearance_menu, "Cell shading…", "set_current_cell_background")
        self._action(self.appearance_menu, "Table properties…", self.table_properties_dialog)
        self.select_menu = self._menu("Select")
        for kind in ("Table", "Row", "Column"):
            self._action(self.select_menu, kind, lambda k=kind: self.select(k))
        self.state_label = QLabel(self)
        self.addWidget(self.state_label)
        self.bind_editor(window.current_editor)

    def _menu(self, title):
        button = QToolButton(self)
        button.setText(title)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(title, button)
        button.setMenu(menu)
        self.addWidget(button)
        self.table_actions.append(button)
        return menu

    def _action(self, owner, text, callback):
        action = QAction(text, self)
        action.triggered.connect(lambda checked=False: callback())
        owner.addAction(action)
        self.table_actions.append(action)
        return action

    def _delegate(self, owner, text, method):
        return self._action(owner, text, lambda: self._invoke(method))

    def _invoke(self, method):
        if self._table() is None:
            return
        try:
            getattr(self.window, method)()
        finally:
            self._finish()

    def bind_editor(self, editor):
        if self.editor is not None:
            for signal in (self.editor.cursorPositionChanged, self.editor.selectionChanged,
                           self.editor.textChanged):
                try:
                    signal.disconnect(self.sync)
                except (TypeError, RuntimeError):
                    pass
        self.editor = editor
        if editor is not None:
            for signal in (editor.cursorPositionChanged, editor.selectionChanged, editor.textChanged):
                signal.connect(self.sync)
        self.sync()

    def _table(self):
        editor = self.window.current_editor
        return editor.textCursor().currentTable() if editor and not editor.isReadOnly() else None

    def sync(self):
        editor = self.window.current_editor
        table = self._table()
        self.insert_action.setEnabled(bool(editor and not editor.isReadOnly()))
        for action in self.table_actions:
            action.setEnabled(table is not None)
        self.state_label.setText("No table")
        if table is not None:
            cursor = editor.textCursor()
            cell = table.cellAt(cursor)
            row, rows, column, columns = cursor.selectedTableCells()
            self.merge_action.setEnabled(rows > 0 and columns > 0 and rows * columns > 1)
            self.split_action.setEnabled(cell.rowSpan() > 1 or cell.columnSpan() > 1)
            self.state_label.setText(
                f"{table.rows()}×{table.columns()} · R{cell.row()+1} C{cell.column()+1}")

    def _finish(self):
        self.sync()
        editor = self.window.current_editor
        if editor:
            editor.setFocus()

    @contextmanager
    def _edit(self):
        editor = self.window.current_editor
        cursor = editor.textCursor()
        saved = QTextCursor(cursor)
        cursor.beginEditBlock()
        try:
            yield
        finally:
            cursor.endEditBlock()
            editor.setTextCursor(saved)
            self._finish()

    @staticmethod
    def _spin(parent, name, low, high, value):
        spin = QSpinBox(parent)
        spin.setObjectName(name)
        spin.setRange(low, high)
        spin.setValue(value)
        return spin

    def insert_table_dialog(self):
        editor = self.window.current_editor
        if not editor or editor.isReadOnly():
            return
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Insert table")
        layout = QFormLayout(dialog)
        rows = self._spin(dialog, "rows", 1, 50, 3)
        columns = self._spin(dialog, "columns", 1, 50, 3)
        header = QCheckBox("Header row", dialog)
        header.setObjectName("header")
        style = QComboBox(dialog)
        style.setObjectName("style")
        style.addItems(STYLES)
        preview = QLabel(dialog)
        preview.setObjectName("preview")
        preview.setWordWrap(True)
        def update_preview():
            description = ("No added colouring", "Blue first row with contrasting text",
                           "Alternating pale blue rows")[style.currentIndex()]
            preview.setText(f"{rows.value()} rows × {columns.value()} columns. {description}. "
                            + ("First row repeats as a header." if header.isChecked() else "No repeating header."))
        for spin in (rows, columns):
            spin.valueChanged.connect(update_preview)
        style.currentIndexChanged.connect(update_preview)
        header.toggled.connect(update_preview)
        update_preview()
        for label, widget in (("Rows", rows), ("Columns", columns), ("Style", style),
                              ("", header), ("Preview", preview)):
            layout.addRow(label, widget)
        self._buttons(dialog, layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.insert_table(rows.value(), columns.value(), style.currentText(), header.isChecked())

    @staticmethod
    def _buttons(dialog, layout):
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

    def insert_table(self, rows, cols, style="Plain", header=False):
        if style not in STYLES or not 1 <= rows <= 50 or not 1 <= cols <= 50:
            raise ValueError("Invalid table dimensions or style")
        editor = self.window.current_editor
        if not editor or editor.isReadOnly():
            return
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        try:
            fmt = QTextTableFormat()
            fmt.setBorder(1)
            fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
            fmt.setCellPadding(6)
            fmt.setCellSpacing(0)
            fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
            fmt.setColumnWidthConstraints(self._widths(cols))
            fmt.setHeaderRowCount(int(header))
            table = cursor.insertTable(rows, cols, fmt)
            self._style(table, style)
        finally:
            cursor.endEditBlock()
        editor.setTextCursor(table.cellAt(0, 0).firstCursorPosition())
        self._finish()
        return table

    @staticmethod
    def _widths(count):
        return [QTextLength(QTextLength.Type.PercentageLength, 100 / count) for _ in range(count)]

    @staticmethod
    def _cells(table):
        seen = set()
        for row in range(table.rows()):
            for col in range(table.columns()):
                cell = table.cellAt(row, col)
                key = cell.firstCursorPosition().position()
                if key not in seen:
                    seen.add(key)
                    yield cell

    def _style(self, table, style):
        for cell in self._cells(table):
            cell_format = cell.format().toTableCellFormat()
            colour = cell_format.background().color().name()
            serialized_kind = None
            if not cell_format.hasProperty(_STYLE_ORIGINAL):
                if colour == "#245a81" and cell.row() == 0:
                    serialized_kind = "header"
                elif colour == "#eaf2f8":
                    serialized_kind = "band"
            blue = style == "Blue header" and cell.row() == 0
            band = style == "Banded rows" and cell.row() % 2 == 1
            changes = {}
            if blue or band:
                changes[QTextFormat.Property.BackgroundBrush] = QBrush(QColor("#245a81" if blue else "#eaf2f8"))
            if blue:
                changes[QTextFormat.Property.ForegroundBrush] = QBrush(QColor("white"))
                changes[QTextFormat.Property.FontWeight] = int(QFont.Weight.Bold)
            elif band:
                changes[QTextFormat.Property.ForegroundBrush] = QBrush(QColor("#202124"))
            cell.setFormat(_decorate(_clear_serialized_style(cell_format, serialized_kind), changes))
            # Work on fragments, not a whole-cell char format: preserve mixed fonts.
            fragments = []
            block = cell.firstCursorPosition().block()
            while block.isValid() and block.position() <= cell.lastCursorPosition().position():
                iterator = block.begin()
                while not iterator.atEnd():
                    fragment = iterator.fragment()
                    if fragment.isValid():
                        fragments.append((fragment.position(), fragment.length(), fragment.charFormat()))
                    iterator += 1
                block = block.next()
            text_changes = {p: v for p, v in changes.items() if p != QTextFormat.Property.BackgroundBrush}
            for pos, length, fmt in fragments:
                cursor = QTextCursor(table.document())
                cursor.setPosition(pos)
                cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(_decorate(_clear_serialized_style(fmt, serialized_kind), text_changes))

    def apply_style(self, style):
        if style not in STYLES:
            raise ValueError("Unknown table style")
        table = self._table()
        if table is not None:
            with self._edit():
                self._style(table, style)

    def fit_width(self):
        table = self._table()
        if table is not None:
            with self._edit():
                fmt = table.format()
                fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
                table.setFormat(fmt)

    def equal_columns(self):
        table = self._table()
        if table is not None:
            with self._edit():
                fmt = table.format()
                fmt.setColumnWidthConstraints(self._widths(table.columns()))
                table.setFormat(fmt)

    def set_table_properties(self, border, padding, width, header):
        table = self._table()
        if table is not None:
            with self._edit():
                fmt = table.format()
                fmt.setBorder(max(0, min(5, border)))
                fmt.setCellPadding(max(0, min(20, padding)))
                fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, max(20, min(100, width))))
                fmt.setHeaderRowCount(int(bool(header)))
                table.setFormat(fmt)

    def table_properties_dialog(self):
        table = self._table()
        if table is None:
            return
        fmt = table.format()
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Table properties")
        layout = QFormLayout(dialog)
        border = self._spin(dialog, "border", 0, 5, round(fmt.border()))
        padding = self._spin(dialog, "padding", 0, 20, round(fmt.cellPadding()))
        width = self._spin(dialog, "width", 20, 100,
                           round(fmt.width().rawValue()) if fmt.width().type() == QTextLength.Type.PercentageLength else 100)
        width.setSuffix("%")
        header = QCheckBox("Header row", dialog)
        header.setObjectName("header")
        header.setChecked(fmt.headerRowCount() > 0)
        for label, widget in (("Border width", border), ("Cell padding", padding),
                              ("Table width", width), ("", header)):
            layout.addRow(label, widget)
        self._buttons(dialog, layout)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_table_properties(border.value(), padding.value(), width.value(), header.isChecked())

    def select(self, kind):
        table = self._table()
        if table is None:
            return
        editor = self.window.current_editor
        cell = table.cellAt(editor.textCursor())
        top, bottom, left, right = 0, table.rows()-1, 0, table.columns()-1
        if kind == "Row":
            top, bottom = cell.row(), cell.row() + cell.rowSpan()-1
        elif kind == "Column":
            left, right = cell.column(), cell.column() + cell.columnSpan()-1
        cursor = table.cellAt(top, left).firstCursorPosition()
        cursor.setPosition(table.cellAt(bottom, right).lastCursorPosition().position(),
                           QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self._finish()

    def show_context_menu(self, editor, point):
        """Point is viewport-local; the caller installs the context-menu hook."""
        cursor = editor.textCursor()
        clicked = editor.cursorForPosition(point)
        inside = (cursor.hasSelection() and
                  cursor.selectionStart() <= clicked.position() <= cursor.selectionEnd())
        if cursor.hasComplexSelection():
            # A rectangular selection is not its linear document range: gaps
            # between selected columns can lie between the two endpoints.
            table = cursor.currentTable()
            inside = False
            if table is not None and clicked.currentTable() == table:
                row, rows, column, columns = cursor.selectedTableCells()
                cell = table.cellAt(clicked)
                inside = (rows > 0 and columns > 0 and
                          cell.row() < row + rows and cell.row() + cell.rowSpan() > row and
                          cell.column() < column + columns and
                          cell.column() + cell.columnSpan() > column)
        if not inside:
            editor.setTextCursor(clicked)
        self.sync()
        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        self.window.font_toolbar.populate_context_menu(menu)
        table_menu = menu.addMenu("Table")
        table_menu.addAction(self.insert_action)
        if clicked.currentTable() is not None:
            table_menu.addSeparator()
            for submenu in (self.row_menu, self.column_menu):
                table_menu.addMenu(submenu)
            table_menu.addAction(self.merge_action)
            table_menu.addAction(self.split_action)
            table_menu.addAction(self.delete_action)
            table_menu.addMenu(self.appearance_menu)
            table_menu.addMenu(self.select_menu)
        try:
            menu.exec(editor.viewport().mapToGlobal(point))
        finally:
            menu.deleteLater()