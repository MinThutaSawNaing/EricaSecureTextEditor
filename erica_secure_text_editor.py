# Erica Secure Text Editor v3.1 – With Font Size Controls (Tested & Working)
import sys, os, json, secrets, re, hmac, ctypes
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QInputDialog,
    QMessageBox, QLineEdit, QStatusBar, QLabel, QDialog,
    QVBoxLayout, QProgressBar, QPushButton, QTabWidget, QTextBrowser
)
from PyQt6.QtGui import QFont, QIcon, QAction, QTextCharFormat, QTextCursor, QTextListFormat, QTextBlockFormat, QBrush, QColor, QDesktopServices
from PyQt6.QtGui import QTextDocumentFragment, QTextTableFormat, QTextFrameFormat
from PyQt6.QtCore import Qt, QTimer, QUrl, QMimeData

# Constants
def ensure_windows_supported():
    if not sys.platform.startswith('win'):
        raise SystemExit("Erica Secure Text Editor is now supported on Windows only.")


def get_config_path():
    appdata = os.getenv('APPDATA') or os.getenv('LOCALAPPDATA')
    if appdata:
        return os.path.join(appdata, 'SecureText')
    return os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'SecureText')


CONFIG_PATH = get_config_path()
CONFIG_FILE = os.path.join(CONFIG_PATH, 'config.json')
DEFAULT_TIMEOUT = 60 * 60  # 1 hour
CLIPBOARD_CLEAR_TIME = 300 * 1000  # 5 minutes in milliseconds
DEFAULT_FONT_SIZE = 12
IMAGE_MAGIC = b"ERICAIMG1"
WINDOWS_APP_ID = "MinThutaSawNaing.EricaSecureTextEditor.3.1"
_CRYPTO_CACHE = None

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def set_windows_app_id():
    if not sys.platform.startswith('win'):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass


def get_crypto():
    global _CRYPTO_CACHE
    if _CRYPTO_CACHE is None:
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding, hashes, hmac as crypto_hmac
        from cryptography.hazmat.backends import default_backend

        _CRYPTO_CACHE = {
            "PBKDF2HMAC": PBKDF2HMAC,
            "Cipher": Cipher,
            "algorithms": algorithms,
            "modes": modes,
            "padding": padding,
            "hashes": hashes,
            "crypto_hmac": crypto_hmac,
            "default_backend": default_backend,
        }
    return _CRYPTO_CACHE



# Cryptography Functions
def derive_key(password: str, salt: bytes) -> bytes:
    crypto = get_crypto()
    kdf = crypto["PBKDF2HMAC"](
        algorithm=crypto["hashes"].SHA256(), length=32, salt=salt,
        iterations=100_000, backend=crypto["default_backend"]()
    )
    return kdf.derive(password.encode())

def compute_hmac(key: bytes, data: bytes) -> bytes:
    crypto = get_crypto()
    signer = crypto["crypto_hmac"].HMAC(
        key, crypto["hashes"].SHA256(), backend=crypto["default_backend"]()
    )
    signer.update(data)
    return signer.finalize()

def encrypt_text(plain: str, password: str) -> bytes:
    return encrypt_bytes(plain.encode(), password)

def decrypt_text(data: bytes, password: str) -> str:
    return decrypt_bytes(data, password).decode()

def encrypt_bytes(raw: bytes, password: str) -> bytes:
    crypto = get_crypto()
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(16)
    key = derive_key(password, salt)
    padder = crypto["padding"].PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    cipher = crypto["Cipher"](
        crypto["algorithms"].AES(key),
        crypto["modes"].CBC(iv),
        backend=crypto["default_backend"](),
    )
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    full_data = salt + iv + encrypted
    tag = compute_hmac(key, full_data)
    return full_data + tag

def decrypt_bytes(data: bytes, password: str) -> bytes:
    crypto = get_crypto()
    if len(data) < 48:
        raise ValueError("Data too short to be valid.")
    salt, iv = data[:16], data[16:32]
    tag = data[-32:]
    encrypted = data[32:-32]
    key = derive_key(password, salt)
    expected_tag = compute_hmac(key, salt + iv + encrypted)
    if not hmac.compare_digest(tag, expected_tag):
        raise IntegrityError("Integrity check failed.")
    cipher = crypto["Cipher"](
        crypto["algorithms"].AES(key),
        crypto["modes"].CBC(iv),
        backend=crypto["default_backend"](),
    )
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = crypto["padding"].PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()

def pack_image_payload(image_bytes: bytes, extension: str) -> bytes:
    ext_bytes = extension.encode("utf-8")
    if len(ext_bytes) > 255:
        raise ValueError("Image extension is too long.")
    return IMAGE_MAGIC + bytes([len(ext_bytes)]) + ext_bytes + image_bytes

def unpack_image_payload(payload: bytes):
    if not payload.startswith(IMAGE_MAGIC) or len(payload) <= len(IMAGE_MAGIC):
        raise ValueError("Invalid encrypted image format.")
    ext_len_index = len(IMAGE_MAGIC)
    ext_len = payload[ext_len_index]
    data_start = ext_len_index + 1 + ext_len
    if data_start > len(payload):
        raise ValueError("Corrupted encrypted image payload.")
    extension = payload[ext_len_index + 1:data_start].decode("utf-8")
    return extension, payload[data_start:]

# Config Management
def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_config(data):
    os.makedirs(CONFIG_PATH, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)

def load_theme():
    return load_config().get("theme", "dark")

def save_theme(mode):
    config = load_config()
    config["theme"] = mode
    save_config(config)

def check_password_strength(password):
    length = len(password) >= 8
    lower = re.search(r"[a-z]", password)
    upper = re.search(r"[A-Z]", password)
    digit = re.search(r"\d", password)
    special = re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)
    score = sum([bool(x) for x in [length, lower, upper, digit, special]])
    return score * 20

class IntegrityError(Exception):
    pass

class PasswordDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Encryption Password")
        self.setFixedWidth(230)
        layout = QVBoxLayout(self)
        
        self.input = QLineEdit(self)
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.setPlaceholderText("Enter your password...")
        layout.addWidget(self.input)
        
        self.strength_bar = QProgressBar(self)
        self.strength_bar.setRange(0, 100)
        self.strength_bar.setTextVisible(True)
        self.strength_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #bbb;
                border-radius: 4px;
                text-align: center;
                font-size: 10px;
                height: 12px;
            }
            QProgressBar::chunk {
                background-color: #007acc;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.strength_bar)
        
        self.ok = QPushButton("OK", self)
        self.ok.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.ok)
        
        self.input.textChanged.connect(self.evaluate)
        self.ok.clicked.connect(self.accept)

    def evaluate(self):
        score = check_password_strength(self.input.text())
        self.strength_bar.setValue(score)
        self.strength_bar.setFormat(f"{score}% Strength")

    def get_password(self):
        return self.input.text() if self.exec() else None
# Add this new class definition
class ClickableTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)  # Disable default Qt link opening (Ctrl+Click)
        self.setMouseTracking(True) # Enable mouse move events even when no button is pressed
        self.setReadOnly(False) # Ensure it's editable by default

    def mouseReleaseEvent(self, event):
        # This method is called when a mouse button is released
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if the mouse was released over an anchor (link)
            anchor = self.anchorAt(event.pos())
            if anchor:
                # If it's a link, open it using QDesktopServices
                QDesktopServices.openUrl(QUrl(anchor))
                return  # Consume the event so the text editor doesn't process it further
        # For any other mouse release event (e.g., not on a link, or right-click),
        # pass it to the base class to handle text selection, etc.
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        # This method is called when the mouse moves over the widget
        # Check if the mouse is currently over an anchor (link)
        anchor = self.anchorAt(event.pos())
        if anchor:
            # If over a link, set the cursor to a pointing hand
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            # Otherwise, set the cursor back to the I-beam (text editing) cursor
            self.setCursor(Qt.CursorShape.IBeamCursor)
        # Pass the event to the base class for default mouse move handling
        super().mouseMoveEvent(event)



class MainWindow(QMainWindow):
    def __init__(self, initial_file=None):
        super().__init__()
        self.setWindowTitle("Erica Secure Text Editor 3.1")
        self.app_icon = QIcon(resource_path("icon.ico"))
        self.setWindowIcon(self.app_icon)
        self.resize(1000, 650)
        app = QApplication.instance()
        app.setWindowIcon(self.app_icon)

        # Initialize UI components
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.setCentralWidget(self.tabs)

        self.open_documents = []  # {'editor': QTextEdit, 'path': str or None, 'password': str or None}
        self.timeout_seconds = DEFAULT_TIMEOUT
        self.remaining_time = self.timeout_seconds
        self.timeout_shutdown_in_progress = False

        # Setup timers
        self.timeout_timer = QTimer()
        self.timeout_timer.timeout.connect(self.handle_timeout_tick)
        self.clipboard_clear_timer = QTimer()
        self.clipboard_clear_timer.setSingleShot(True)
        self.clipboard_clear_timer.timeout.connect(self.clear_clipboard)

        self.init_menu()
        self.init_status()
        self.set_theme(load_theme())

        # Show an empty editor first so the window can render quickly even on low-RAM devices.
        self.add_new_tab()
        if initial_file:
            QTimer.singleShot(0, lambda: self.open_file(initial_file))

        self.reset_idle_timer()

    # Properties
    @property
    def current_editor(self):
        current_index = self.tabs.currentIndex()
        if current_index == -1 or not self.open_documents or current_index >= len(self.open_documents):
            return None
        return self.open_documents[current_index]['editor']

    @property
    def current_file_path(self):
        current_index = self.tabs.currentIndex()
        if current_index == -1 or not self.open_documents or current_index >= len(self.open_documents):
            return None
        return self.open_documents[current_index]['path']

    def set_current_file_path(self, path):
        current_index = self.tabs.currentIndex()
        if current_index != -1 and self.open_documents and current_index < len(self.open_documents):
            self.open_documents[current_index]['path'] = path
            self.tabs.setTabText(current_index, os.path.basename(path) if path else "Untitled")

    def set_current_password(self, password):
        current_index = self.tabs.currentIndex()
        if current_index != -1 and self.open_documents and current_index < len(self.open_documents):
            self.open_documents[current_index]['password'] = password

    def get_current_password(self):
        current_index = self.tabs.currentIndex()
        if current_index == -1 or not self.open_documents or current_index >= len(self.open_documents):
            return None
        return self.open_documents[current_index].get('password')

    # Text Formatting Methods
    def apply_bold(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            fmt = cursor.charFormat()
            is_bold = fmt.fontWeight() == QFont.Weight.Bold
            fmt.setFontWeight(QFont.Weight.Bold if not is_bold else QFont.Weight.Normal)
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            # print("Bold applied successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to apply bold: {e}")
            import traceback
            traceback.print_exc()

    def apply_italic(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            fmt = cursor.charFormat()
            fmt.setFontItalic(not fmt.fontItalic())
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            # print("Italic applied successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to apply italic: {e}")
            import traceback
            traceback.print_exc()

    def increase_font_size(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            fmt = cursor.charFormat()
            current_size = fmt.fontPointSize()
            fmt.setFontPointSize(current_size + 1 if current_size > 0 else DEFAULT_FONT_SIZE + 1)
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            # print("Font size increased successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to increase font size: {e}")
            import traceback
            traceback.print_exc()

    def decrease_font_size(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            fmt = cursor.charFormat()
            current_size = fmt.fontPointSize()
            if current_size > 1:
                fmt.setFontPointSize(current_size - 1)
                cursor.mergeCharFormat(fmt)
                editor.setTextCursor(cursor)
                # print("Font size decreased successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to decrease font size: {e}")
            import traceback
            traceback.print_exc()

    def apply_bullet_list(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            cursor.createList(QTextListFormat.Style.ListDisc)
            editor.setTextCursor(cursor)
            # print("Bullet list applied successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to apply bullet list: {e}")
            import traceback
            traceback.print_exc()

    def apply_numbered_list(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()
            cursor.createList(QTextListFormat.Style.ListDecimal)
            editor.setTextCursor(cursor)
            # print("Numbered list applied successfully.") # Optional: for debugging
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to apply numbered list: {e}")
            import traceback
            traceback.print_exc()

    def openExternalLink(self, url):
        """Open clicked links in default browser"""
        QDesktopServices.openUrl(QUrl(url))

    def insert_table(self):
        editor = self.current_editor
        if not editor or editor.isReadOnly():
            return

        rows, ok = QInputDialog.getInt(self, "Insert Table", "Rows:", 2, 1, 20)
        if not ok:
            return

        columns, ok = QInputDialog.getInt(self, "Insert Table", "Columns:", 2, 1, 10)
        if not ok:
            return

        try:
            cursor = editor.textCursor()
            table_format = QTextTableFormat()
            table_format.setBorder(1)
            table_format.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            table_format.setCellPadding(6)
            table_format.setCellSpacing(0)
            table_format.setHeaderRowCount(1 if rows > 1 else 0)
            cursor.insertTable(rows, columns, table_format)
            editor.setFocus()
            editor.document().setModified(True)
        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to insert table: {e}")

# Proper insert_link implementation
    def insert_link(self):
        editor = self.current_editor
        if not editor or editor.isReadOnly():
            return

        cursor = editor.textCursor()
        selected_text = cursor.selectedText().strip()

        link_text, ok = QInputDialog.getText(self, "Insert Link", "Link text:", text=selected_text)
        if not ok or not link_text:
            return

        url, ok = QInputDialog.getText(self, "Insert Link", "URL:", text="https://")
        if not ok or not url:
            return

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        cursor.beginEditBlock()
        cursor.removeSelectedText()
        cursor.insertHtml(f'<a href="{url}">{link_text}</a>')
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, 1)
        editor.setTextCursor(cursor)

        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(QColor("black")))
        fmt.setFontUnderline(False)
        fmt.setAnchor(False)

        cursor.setCharFormat(fmt)
        editor.setCurrentCharFormat(fmt)
        cursor.endEditBlock()

        editor.setFocus()
        editor.document().setModified(True)

    def clear_format(self):
        editor = self.current_editor
        if not editor:
            return
        try:
            cursor = editor.textCursor()

            # Select entire document or selection
            if not cursor.hasSelection():
                cursor.select(QTextCursor.SelectionType.Document)

            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Weight.Normal)
            fmt.setFontItalic(False)
            fmt.setFontUnderline(False)
            fmt.setFontPointSize(DEFAULT_FONT_SIZE)
            fmt.setForeground(QBrush(QColor("black")))
            fmt.setAnchor(False)

            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
            editor.setCurrentCharFormat(fmt)

            # Remove bullet/number lists
            current_list = cursor.currentList()
            if current_list:
                block_format = QTextBlockFormat()
                cursor.setBlockFormat(block_format)

        except Exception as e:
            QMessageBox.critical(self, "Formatting Error", f"Failed to clear format: {e}")
            import traceback
            traceback.print_exc()



    # Core Editor Methods
    def on_tab_changed(self, index):
        if index != -1 and index < len(self.open_documents):
            current_doc = self.open_documents[index]
            editor = current_doc['editor']
            
            # Reconnect editor signals
            try:
                editor.cursorPositionChanged.disconnect()
                editor.textChanged.disconnect()
            except TypeError:
                pass
                
            editor.cursorPositionChanged.connect(self.update_status)
            editor.textChanged.connect(self.reset_idle_timer)
            
            self.update_status()
            self.status.showMessage(f"Active: {os.path.basename(current_doc['path']) if current_doc['path'] else 'Untitled'}")
        else:
            self.status.showMessage("No active tab")
            self.update_status()

    

    def _create_editor_instance(self):
        """
        Helper method to create and configure a new ClickableTextBrowser instance.
        This centralizes editor setup to reduce human error and ensure consistency.
        """
        editor = ClickableTextBrowser(self) # Use our custom class
        
        # Basic editor properties
        editor.setFont(QFont("Fira Code", DEFAULT_FONT_SIZE))
        editor.setAcceptRichText(True)
        
        # Connect essential signals for status updates and idle timer.
        # These connections are crucial for the editor's functionality within the main window.
        editor.cursorPositionChanged.connect(self.update_status)
        editor.textChanged.connect(self.reset_idle_timer)
        
        return editor

    def add_new_tab(self, file_path=None, content="", content_is_html=False):
        """
        Adds a new tab to the QTabWidget, creating a new editor instance
        using the _create_editor_instance helper.
        
        Args:
            file_path (str, optional): The path to the file being opened.
                                       If None, the tab is "Untitled".
            content (str, optional): The initial content for the editor.
                                     Can be plain text or HTML.
        """
        # 1. Create the editor instance using the centralized helper method.
        #    This ensures all new editors are correctly configured with direct-click
        #    link support and hover cursor changes.
        editor = self._create_editor_instance()
        
        # 2. Add the editor and its associated file path to our internal list
        #    of open documents. This list helps manage multiple tabs.
        self.open_documents.append({'editor': editor, 'path': file_path, 'password': None})
        
        # 3. Determine the title for the new tab. If a file_path is provided,
        #    use its base name; otherwise, default to "Untitled".
        tab_title = os.path.basename(file_path) if file_path else "Untitled"
        
        # 4. Add the newly created editor widget as a tab to the QTabWidget.
        #    Then, set this new tab as the currently active tab.
        tab_index = self.tabs.addTab(editor, tab_title)
        self.tabs.setCurrentIndex(tab_index)

        # 5. Set the initial content of the editor.
        #    Decrypted Erica documents are stored as HTML, but plain text content
        #    may also contain angle brackets and should not be treated as markup.
        if content_is_html:
            editor.setHtml(content)
        else:
            editor.setPlainText(content)
            
        # 6. Mark the document as unmodified initially. This is important
        #    so the application doesn't prompt to save an empty or just-opened file.
        editor.document().setModified(False)

        # 7. Update the status bar to inform the user about the new tab.
        self.status.showMessage(f"Active: {tab_title}")

    def close_tab(self, index):
        if index < 0 or index >= len(self.open_documents):
            return
            
        editor = self.open_documents[index]['editor']
        
        # Prompt to save if modified
        if editor.document().isModified():
            reply = QMessageBox.question(
                self,
                "Save Changes?",
                f"Save changes to {self.tabs.tabText(index)}?",
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Save:
                self.silent_save(index)
                if editor.document().isModified():  # Save failed or cancelled
                    return

        # Remove tab
        self._disconnect_editor_signals(index)
        self.tabs.removeTab(index)
        del self.open_documents[index]
        
        # Create new tab if none left
        if not self.tabs.count():
            self.add_new_tab()

    def prompt_password(self, title, show_strength=False):
        if show_strength:
            dialog = PasswordDialog(self)
            dialog.setWindowTitle(title)
            return dialog.get_password()
        else:
            password, ok = QInputDialog.getText(
                self, title, "Enter password:", QLineEdit.EchoMode.Password
            )
            return password if ok else None

    def silent_save(self, index):
        editor = self.open_documents[index]['editor']
        file_path = self.open_documents[index]['path']
        
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save As Encrypted",
                "",
                "Encrypted Files (*.enc)"
            )
            if not file_path:
                return False
            self.open_documents[index]['path'] = file_path
            
        password = self.open_documents[index].get('password')
        if not password:
            password = self.prompt_password("Encrypt File", show_strength=True)
        if not password:
            return False
            
        try:
            encrypted = encrypt_text(editor.toHtml(), password)
            self._ensure_file_writable(file_path)
            with open(file_path, 'wb') as f:
                f.write(encrypted)
                
            os.chmod(file_path, 0o444)  # Read-only
            editor.document().setModified(False)
            self.open_documents[index]['password'] = password
            self.tabs.setTabText(index, os.path.basename(file_path))
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")
            return False

    def _disconnect_editor_signals(self, index):
        editor = self.open_documents[index]['editor']
        try:
            editor.cursorPositionChanged.disconnect()
            editor.textChanged.disconnect()
        except TypeError:
            pass

    def _ensure_file_writable(self, path):
        if os.path.exists(path):
            os.chmod(path, 0o666)

    def encrypt_image_file(self):
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image to Encrypt",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff)"
        )
        if not image_path:
            return

        default_name = os.path.splitext(os.path.basename(image_path))[0] + ".eimg"
        encrypted_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Encrypted Image",
            default_name,
            "Erica Encrypted Image (*.eimg)"
        )
        if not encrypted_path:
            return

        password = self.prompt_password("Encrypt Image", show_strength=True)
        if not password:
            return

        try:
            with open(image_path, 'rb') as image_file:
                image_bytes = image_file.read()

            payload = pack_image_payload(image_bytes, os.path.splitext(image_path)[1])
            encrypted = encrypt_bytes(payload, password)
            self._ensure_file_writable(encrypted_path)
            with open(encrypted_path, 'wb') as encrypted_file:
                encrypted_file.write(encrypted)

            os.chmod(encrypted_path, 0o444)
            self.status.showMessage(f"Encrypted image: {os.path.basename(encrypted_path)}")
            QMessageBox.information(self, "Image Encrypted", "Image encrypted successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Image encryption failed: {e}")

    def decrypt_image_file(self):
        encrypted_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Encrypted Image",
            "",
            "Erica Encrypted Image (*.eimg)"
        )
        if not encrypted_path:
            return

        password = self.prompt_password("Decrypt Image")
        if not password:
            return

        try:
            with open(encrypted_path, 'rb') as encrypted_file:
                encrypted_data = encrypted_file.read()

            payload = decrypt_bytes(encrypted_data, password)
            original_extension, image_bytes = unpack_image_payload(payload)
            default_name = os.path.splitext(os.path.basename(encrypted_path))[0] + original_extension
            output_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Decrypted Image",
                default_name,
                f"Image Files (*{original_extension});;All Files (*)"
            )
            if not output_path:
                return

            self._ensure_file_writable(output_path)
            with open(output_path, 'wb') as output_file:
                output_file.write(image_bytes)

            self.status.showMessage(f"Decrypted image: {os.path.basename(output_path)}")
            QMessageBox.information(self, "Image Decrypted", "Image decrypted successfully.")
        except IntegrityError:
            QMessageBox.critical(self, "Integrity Error", "Encrypted image is tampered with or corrupted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Image decryption failed: {e}")

    # File Operations
    def open_file(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open Encrypted File", 
                "", 
                "Encrypted Files (*.enc)"
            )
            if not path:
                return

        # Check if already open
        for i, doc in enumerate(self.open_documents):
            if doc['path'] == path:
                self.tabs.setCurrentIndex(i)
                QMessageBox.information(
                    self,
                    "File Already Open",
                    f"'{os.path.basename(path)}' is already open."
                )
                return

        password = self.prompt_password("Decrypt File")
        if not password:
            return

        try:
            with open(path, 'rb') as f:
                data = f.read()
                
            text = decrypt_text(data, password)
            
            # Use current tab if empty, otherwise new tab
            if (self.current_editor and not self.current_file_path 
                    and not self.current_editor.toPlainText()):
                self.current_editor.setHtml(text)
                self.set_current_file_path(path)
                self.set_current_password(password)
                self.current_editor.document().setModified(False)
                self.status.showMessage(f"Opened: {os.path.basename(path)}")
            else:
                self.add_new_tab(file_path=path, content=text, content_is_html=True)
                self.open_documents[self.tabs.currentIndex()]['password'] = password
                self.status.showMessage(f"Opened: {os.path.basename(path)}")
                
        except IntegrityError:
            QMessageBox.critical(self, "Integrity Error", 
                "File appears tampered with or corrupted.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Decryption failed: {e}")

    def save_file(self):
        if not self.current_editor:
            QMessageBox.warning(self, "No Editor", "No active editor to save.")
            return

        if self.current_file_path:
            try:
                password = self.get_current_password()
                if not password:
                    # Read existing file to determine if it's encrypted
                    with open(self.current_file_path, 'rb') as f:
                        data = f.read()

                    # If data exists and is long enough to be encrypted, prompt for existing password
                    # Otherwise, it's a new file or an unencrypted file being saved for the first time
                    if len(data) >= 48: # Minimum size for salt (16) + IV (16) + HMAC (32)
                        password = self.prompt_password("Enter Password")
                    else:
                        password = self.prompt_password("Set Password", show_strength=True)
                    
                if not password:
                    return
                    
                encrypted = encrypt_text(self.current_editor.toHtml(), password)
                self._ensure_file_writable(self.current_file_path)
                with open(self.current_file_path, 'wb') as f:
                    f.write(encrypted)
                    
                os.chmod(self.current_file_path, 0o444)
                self.set_current_password(password)
                self.current_editor.document().setModified(False)
                msg = f"Saved: {os.path.basename(self.current_file_path)}"
                self.status.showMessage(msg)
                
                # Prompt to clear editor
                reply = QMessageBox.question(
                    self,
                    "Clear Editor?",
                    "File saved. Clear editor content?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.secure_clear_editor()
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Save failed: {e}")
        else:
            self.save_as_file()

    def save_as_file(self):
        if not self.current_editor:
            QMessageBox.warning(self, "No Editor", "No active editor to save.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As Encrypted",
            "",
            "Encrypted Files (*.enc)"
        )
        if not path:
            return
            
        password = self.prompt_password("Encrypt File", show_strength=True)
        if not password:
            return

        try:
            encrypted = encrypt_text(self.current_editor.toHtml(), password)
            self._ensure_file_writable(path)
            with open(path, 'wb') as f:
                f.write(encrypted)
                
            os.chmod(path, 0o444)
            self.set_current_file_path(path)
            self.set_current_password(password)
            self.current_editor.document().setModified(False)
            msg = f"Saved As: {os.path.basename(path)}"
            self.status.showMessage(msg)
            
            # Prompt to clear editor
            reply = QMessageBox.question(
                self,
                "Clear Editor?",
                "File saved. Clear editor content?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.secure_clear_editor()
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save As failed: {e}")

    def new_file(self):
        self.add_new_tab()
        self.status.showMessage("New file started")

    # Clipboard Management
    def secure_copy(self):
        if not self.current_editor:
            return

        
        cursor = self.current_editor.textCursor()
        if cursor.hasSelection():
            selection = QTextDocumentFragment(cursor)
            mime_data = QMimeData()
            mime_data.setHtml(selection.toHtml())
            mime_data.setText(cursor.selectedText())
            QApplication.clipboard().setMimeData(mime_data)
            self.clipboard_clear_timer.start(CLIPBOARD_CLEAR_TIME)
            QMessageBox.information(
                self,
                "Clipboard",
                "Copied. Will auto-clear in 5 mins."
            )

    def clear_clipboard(self):
        QApplication.clipboard().clear()
        QMessageBox.information(self, "Clipboard", "Clipboard cleared.")

    def secure_clear_editor(self):
        if not self.current_editor:
            return
            
        self.current_editor.setPlainText("0" * len(self.current_editor.toPlainText()))
        QTimer.singleShot(100, self.current_editor.clear)
        self.set_current_file_path(None)
        self.set_current_password(None)
        self.current_editor.document().setModified(False)
        self.tabs.setCurrentIndex(self.tabs.currentIndex())  # Refresh tab
        QMessageBox.information(self, "Secure Clear", "Editor cleared.")
        
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)

    # Status Bar
    def update_status(self):
        if not self.current_editor:
            self.status.showMessage("No active editor.")
            return
            
        cursor = self.current_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.positionInBlock() + 1
        words = len(self.current_editor.toPlainText().split())
        self.status.showMessage(f"Ln {line}, Col {col} | Words: {words}")

    # Timer Functions
    def set_idle_timeout(self, seconds):
        self.timeout_seconds = seconds
        self.reset_idle_timer()
        msg = f"Auto-lock set to {seconds // 60} min."
        QMessageBox.information(self, "Timer", msg)

    def reset_idle_timer(self):
        if self.timeout_shutdown_in_progress:
            return
        self.remaining_time = self.timeout_seconds
        self.timeout_timer.start(1000)

    def handle_timeout_tick(self):
        if self.timeout_shutdown_in_progress:
            return

        self.remaining_time -= 1
        mins = self.remaining_time // 60
        secs = self.remaining_time % 60
        self.time_label.setText(f"⏱ Lock in: {mins}:{secs:02d}")
        
        if self.remaining_time <= 0:
            self.timeout_shutdown_in_progress = True
            self.timeout_timer.stop()
            QMessageBox.warning(self, "Auto Lock", "Timer exceeded. Erica will now close.")
            QApplication.instance().quit()

    # View Actions
    def zoom_in(self):
        if self.current_editor:
            self.current_editor.zoomIn()

    def zoom_out(self):
        if self.current_editor:
            self.current_editor.zoomOut()

    def reset_zoom(self):
        if self.current_editor:
            self.current_editor.setFont(QFont("Fira Code", DEFAULT_FONT_SIZE))

    # Theme Management
    def toggle_theme(self):
        current = load_theme()
        new_theme = 'dark' if current == 'light' else 'light'
        save_theme(new_theme)
        self.set_theme(new_theme)

    def set_theme(self, mode):
        close_icon_path = resource_path("closebutton.png").replace("\\", "/")
        dark_theme = f"""
            QMainWindow {{
                background-color: #1e1e1e;
                color: #ffffff;
            }}
            QTextBrowser {{
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #444;
            }}
            QMenuBar, QStatusBar {{
                background-color: #2d2d30;
                color: #ccc;
            }}
            QMenuBar::item {{
                background: transparent;
                color: #ccc;
                padding: 6px 12px;
                margin: 2px 4px;
                border-radius: 4px;
            }}
            QMenuBar::item:selected {{
                background-color: #3a3a3d;
            }}
            QMenuBar::item:pressed {{
                background-color: #444;
            }}
            QMenu {{
                background-color: #2d2d30;
                color: #ccc;
                border: 1px solid #444;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 8px 28px 8px 12px;
                margin: 2px 4px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: #444;
                color: #ffffff;
            }}
            QMenu::separator {{
                height: 1px;
                background: #555;
                margin: 6px 8px;
            }}
            QTabWidget::pane {{
                border: 1px solid #444;
                background-color: #1e1e1e;
            }}
            QTabBar::tab {{
                background: #2d2d30;
                color: #ccc;
                border: 1px solid #444;
                border-bottom-color: #2d2d30;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 10px;
            }}
            QTabBar::tab:selected {{
                background: #252526;
                border-bottom-color: #252526;
            }}
            QTabBar::tab:hover {{
                background: #3a3a3d;
            }}
            QTabBar::close-button {{ image: url({close_icon_path}); }}
            QTabBar::close-button:hover {{
                background: #555;
            }}
        """
        
        light_theme = """
            QMainWindow {
                background-color: #f0f0f0;
                color: #333333;
            }
            QTextBrowser {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #ccc;
            }
            QMenuBar, QStatusBar {
                background-color: #e0e0e0;
                color: #333;
            }
            QMenuBar::item {
                background: transparent;
                color: #333;
                padding: 6px 12px;
                margin: 2px 4px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #ddd;
            }
            QMenuBar::item:pressed {
                background-color: #d0d0d0;
            }
            QMenu {
                background-color: #ffffff;
                color: #333;
                border: 1px solid #ccc;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 28px 8px 12px;
                margin: 2px 4px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #ddd;
                color: #000;
            }
            QMenu::separator {
                height: 1px;
                background: #ccc;
                margin: 6px 8px;
            }
            QTabWidget::pane {
                border: 1px solid #ccc;
                background-color: #f0f0f0;
            }
            QTabBar::tab {
                background: #e0e0e0;
                color: #333;
                border: 1px solid #ccc;
                border-bottom-color: #e0e0e0;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 5px 10px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border-bottom-color: #ffffff;
            }
            QTabBar::tab:hover {
                background: #f5f5f5;
            }
        """
        
        self.setStyleSheet(dark_theme if mode == 'dark' else light_theme)

    # File Permissions
    def make_file_writable(self):
        if not self.current_file_path:
            QMessageBox.information(self, "No File", "No file to unlock.")
            return
            
        confirm = QMessageBox.question(
            self,
            "Unlock File",
            "Remove read-only protection?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                os.chmod(self.current_file_path, 0o666)
                QMessageBox.information(self, "Unlocked", "File is now writable.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not unlock: {e}")

    def lock_file(self):
        if not self.current_file_path:
            QMessageBox.information(self, "No File", "No file to lock.")
            return
            
        confirm = QMessageBox.question(
            self,
            "Lock File",
            "Make file read-only?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                os.chmod(self.current_file_path, 0o444)
                QMessageBox.information(self, "Locked", "File is now read-only.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not lock: {e}")

    # Menu Initialization
    def init_menu(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        # File Menu
        file_menu = menubar.addMenu("File")

        new_action = QAction("New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_file)
        file_menu.addAction(new_action)

        open_action = QAction("Open Encrypted", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction("Save Encrypted", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As Encrypted", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_as_file)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        encrypt_image_action = QAction("Encrypt Image", self)
        encrypt_image_action.triggered.connect(self.encrypt_image_file)
        file_menu.addAction(encrypt_image_action)

        decrypt_image_action = QAction("Decrypt Image", self)
        decrypt_image_action.triggered.connect(self.decrypt_image_file)
        file_menu.addAction(decrypt_image_action)

        file_menu.addSeparator()

        unlock_action = QAction("Unlock File", self)
        unlock_action.triggered.connect(self.make_file_writable)
        file_menu.addAction(unlock_action)

        lock_action = QAction("Lock File", self)
        lock_action.triggered.connect(self.lock_file)
        file_menu.addAction(lock_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit Menu
        edit_menu = menubar.addMenu("Edit")

        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(lambda: self.current_editor.undo() if self.current_editor else None)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(lambda: self.current_editor.redo() if self.current_editor else None)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cut", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(lambda: self.current_editor.cut() if self.current_editor else None)
        edit_menu.addAction(cut_action)

        copy_action = QAction("Copy", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.secure_copy)
        edit_menu.addAction(copy_action)

        paste_action = QAction("Paste", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(lambda: self.current_editor.paste() if self.current_editor else None)
        edit_menu.addAction(paste_action)

        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(lambda: self.current_editor.selectAll() if self.current_editor else None)
        edit_menu.addAction(select_all_action)

        edit_menu.addSeparator()

        secure_clear_action = QAction("Secure Clear", self)
        secure_clear_action.triggered.connect(self.secure_clear_editor)
        edit_menu.addAction(secure_clear_action)

        # Format Menu
        format_menu = menubar.addMenu("Format")

        # Font Controls
        font_menu = format_menu.addMenu("Font")

        bold_action = QAction("Bold", self)
        bold_action.setShortcut("Ctrl+B")
        bold_action.triggered.connect(self.apply_bold)
        font_menu.addAction(bold_action)

        italic_action = QAction("Italic", self)
        italic_action.setShortcut("Ctrl+I")
        italic_action.triggered.connect(self.apply_italic)
        font_menu.addAction(italic_action)

        font_menu.addSeparator()

        inc_size_action = QAction("Increase Size", self)
        inc_size_action.setShortcut("Ctrl++")
        inc_size_action.triggered.connect(self.increase_font_size)
        font_menu.addAction(inc_size_action)

        dec_size_action = QAction("Decrease Size", self)
        dec_size_action.setShortcut("Ctrl+-")
        dec_size_action.triggered.connect(self.decrease_font_size)
        font_menu.addAction(dec_size_action)

        reset_size_action = QAction("Reset Size", self)
        reset_size_action.setShortcut("Ctrl+0")
        reset_size_action.triggered.connect(self.reset_zoom)
        font_menu.addAction(reset_size_action)

        # Lists
        format_menu.addSeparator()

        bullet_list_action = QAction("Bulleted List", self)
        bullet_list_action.triggered.connect(self.apply_bullet_list)
        format_menu.addAction(bullet_list_action)

        numbered_list_action = QAction("Numbered List", self)
        numbered_list_action.triggered.connect(self.apply_numbered_list)
        format_menu.addAction(numbered_list_action)

        table_action = QAction("Insert Table", self)
        table_action.triggered.connect(self.insert_table)
        format_menu.addAction(table_action)

        # Links
        format_menu.addSeparator()

        insert_link_action = QAction("Insert Link", self)
        insert_link_action.triggered.connect(self.insert_link)
        format_menu.addAction(insert_link_action)

        # Clear Format
        format_menu.addSeparator()

        clear_format_action = QAction("Clear Formatting", self)
        clear_format_action.triggered.connect(self.clear_format)
        format_menu.addAction(clear_format_action)

        # View Menu
        view_menu = menubar.addMenu("View")

        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("Reset Zoom", self)
        reset_zoom_action.triggered.connect(self.reset_zoom)
        view_menu.addAction(reset_zoom_action)

        view_menu.addSeparator()

        theme_action = QAction("Toggle Dark Mode", self)
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)

        # Timer Menu
        timer_menu = menubar.addMenu("Timer")
        
        durations = [
            ("15 Minutes", 900),
            ("30 Minutes", 1800),
            ("60 Minutes", 3600),
            ("120 Minutes", 7200)
        ]
        
        for label, seconds in durations:
            action = QAction(label, self)
            action.triggered.connect(lambda _, s=seconds: self.set_idle_timeout(s))
            timer_menu.addAction(action)

        # Help Menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About Erica", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        

    def init_status(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        
        self.time_label = QLabel()
        self.status.addPermanentWidget(self.time_label)
        
        self.update_status()

    def show_about(self):
        QMessageBox.information(
            self,
            "About Erica",
            "Erica Secure Text Editor v3.1\n"
            "––––––––––––––––––––––––––––––––––––––––––––––––––––––\n"
            "This application was proudly developed by Min Thuta Saw Naing (Eric),\n"
            "a Network Security Engineer from Myanmar.\n\n"
            "Erica empowers users with local-only, secure text encryption — designed\n"
            "to be simple, elegant, and professionally hardened.\n\n"
            "🔐 Key Features in v3.1:\n"
            "• AES-256 encryption with HMAC-SHA256 integrity validation\n"
            "• Secure auto-lock timer with user-controlled duration\n"
            "• Clipboard auto-clear after 5 minutes\n"
            "• Files saved as read-only with manual unlock option\n"
            "• Password strength meter during encryption setup\n"
            "• Secure editor wipe after saving\n"
            "• Multi-tab support for concurrent editing\n"
            "• Standard keyboard shortcuts for common actions\n\n"
            "🧪 Special Thanks:\n"
            "• Sai Nay Zin Tun – Penetration Tester, for security audit and reporting\n"
            "  sainayzintun@skillforgemm.com\n"
            "• Bhone Pyae Thway – Software Tester, for QA and functional testing\n"
            "  bhonepyae359@gmail.com\n\n"
            "🌐 Website developed by Wai Yan Htun\n"
            "Contact: waiyantun2919@gmail.com\n\n"
            "For more apps or inquiries: minthuta2612@gmail.com"

        )

if __name__ == '__main__':
    ensure_windows_supported()
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Erica Secure Text Editor")

    # Handle file argument
    initial_file = None
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        initial_file = sys.argv[1]

    window = MainWindow(initial_file)
    window.show()
    sys.exit(app.exec())

