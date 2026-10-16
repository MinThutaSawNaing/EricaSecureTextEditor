# Erica Secure Text Editor

Erica Secure Text Editor is a Windows desktop application for writing, encrypting, and managing sensitive notes entirely on the local machine. It combines a rich-text editing workflow with file-level encryption, recovery safeguards, and packaged desktop delivery through PyQt6, PyInstaller, and Inno Setup.

This project is a strong portfolio example of applied desktop engineering: secure local data handling, UI development, state management, packaging, and automated test coverage in a single Python codebase.

## Download

Download the Windows builds directly from the committed [`release/`](./release/) folder:

- Recommended installer: [Download Erica 3.4 for Windows](./release/EricaSecureTextEditorSetup_3.4.exe?raw=true)
- Portable executable: [Download without installation](./release/EricaSecureTextEditor.exe?raw=true)
- Integrity checks: [`SHA256SUMS.txt`](./release/SHA256SUMS.txt)

The installer is recommended: fresh installations default to the current user without administrator access, with an all-users option when needed. It adds a Start Menu shortcut, offers an optional desktop shortcut, and registers `.erica` Open With support without changing your default app. Existing installations retain their scope and directory when detected.

### What's fixed in 3.4

- Tables use the editor width and put the cursor in the first cell after insertion.
- Row and column deletion keep the cursor in the table; deleting the last row or column removes the table.
- **Format → Tables → Delete Current Table** removes a whole table without using the clipboard.
- Undo/redo is enabled, and empty-table documents are included in recovery snapshots.

These builds are not code-signed; a SHA-256 checksum checks file integrity but does not replace publisher authentication. Windows may show an unknown-publisher warning.

## Project Snapshot

- Built with Python and PyQt6 for a native-style desktop experience
- Uses AES-based encrypted file storage with HMAC integrity validation
- Keeps user data local with no cloud sync, account system, or backend dependency
- Supports secure editing workflows such as password-protected saves, clipboard clearing, and idle lock behavior
- Includes Windows packaging for executable and installer distribution
- Backed by unit tests for encryption, recovery, session metadata, save flows, timeout logic, and table editing behavior

## Why This Project Stands Out

Erica is more than a text editor. It demonstrates the ability to design and ship a complete product with attention to security, usability, and deployment.

From a recruiter or hiring-manager perspective, this repository highlights:

- Desktop application architecture in Python
- Secure file handling and local-first design thinking
- GUI development with custom workflows and multi-tab editing
- State persistence for theme, recent files, and session recovery
- Practical product engineering with installer/build tooling
- Automated testing for critical application behaviors

## Core Features

### Security

- Encrypted document save and open flow
- New secure documents save with the `.erica` extension while legacy `.enc` files remain supported
- HMAC-SHA256 integrity checks to detect tampering or corruption
- Password prompt and password strength feedback during secure save flows
- Idle timeout with auto-lock style shutdown behavior
- Clipboard auto-clear for copied sensitive content
- Read-only protection applied to encrypted output files after save
- Encrypted recovery snapshots for unsaved work
- Recovery key is protected with Windows DPAPI before being written to local config storage
- External links from note content are restricted to `http` and `https`

### Editor Experience

- Multi-tab document editing
- Rich-text formatting with bold, italic, font sizing, lists, and links
- Table insertion and table editing operations
- Zoom controls and status updates
- Theme toggle support
- Recent files tracking
- Reopen last session support

### Secure Asset Handling

- Encrypt image files to protected payloads
- Decrypt encrypted image payloads back to their original format

### Distribution

- PyInstaller spec for generating a Windows executable
- Inno Setup script for creating a Windows installer
- Installer registers Erica in Windows `Open with` for `.erica` documents
- `release/` folder for distributable Windows artifacts
- Application icon and packaged UI assets included in the repo

## Tech Stack

- Python 3
- PyQt6
- cryptography
- PyInstaller
- Inno Setup
- unittest

## Architecture Highlights

The application is implemented in a single primary desktop entrypoint, [`erica_secure_text_editor.py`](./erica_secure_text_editor.py), which combines:

- encryption and decryption utilities
- configuration and session persistence
- secure recovery snapshot handling
- rich-text editor actions
- multi-tab document management
- Windows-oriented desktop packaging support

Supporting project files:

- [`erica_secure_text_editor.spec`](./erica_secure_text_editor.spec) for executable builds
- [`erica_secure_text_editor.iss`](./erica_secure_text_editor.iss) for installer creation
- [`release/README.md`](./release/README.md) for release artifact notes
- [`test_erica_secure_text_editor.py`](./test_erica_secure_text_editor.py) for automated verification

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Build the Rust storage module

Install a 64-bit Windows Rust MSVC toolchain and Visual Studio C++ Build Tools, then run:

```powershell
& 'D:\Erica Text Editor\EricaSecureTextEditor\build_native.ps1'
```

This runs the native tests and builds `erica_storage.dll` offline with no third-party Rust dependencies. Rebuild it after changing the native source. The DLL is required for running from source; there is no silent Python storage fallback. Packaged applications bundle it automatically.

### 3. Run the application

```bash
python erica_secure_text_editor.py
```

## Build for Windows

For the complete test, executable, installer, and checksum pipeline, run:

```powershell
& 'D:\Erica Text Editor\EricaSecureTextEditor\build_windows.ps1'
```

Requires 64-bit Windows Python with the dependencies and PyInstaller installed, the Windows Rust MSVC toolchain with C++ Build Tools, plus Inno Setup 6. The script builds/tests the native module first and does not install dependencies or upload files. Override `-PythonExe` or `-IsccExe` if necessary.

### Create the executable

```bash
pyinstaller erica_secure_text_editor.spec
```

The generated executable is placed in `dist/`.

### Create the installer script output

Use the included Inno Setup script after the executable has been built:

```bash
iscc erica_secure_text_editor.iss
```

The installer is written to `release/` as `EricaSecureTextEditorSetup_3.4.exe`.

### Release folder

The `release/` folder is intended to hold the Windows deliverables for sharing or publishing:

- `EricaSecureTextEditor.exe`
- `EricaSecureTextEditorSetup_3.4.exe`
- `erica_secure_text_editor.iss`

This keeps the checked-in distribution artifacts separate from the transient `dist/` and `build/` directories.

## Run Tests

```bash
python -m unittest discover -v
```

Current automated coverage includes:

- encryption and decryption roundtrip behavior
- recent files and last-session persistence
- encrypted recovery snapshot creation and restore validation
- recovery-key migration and protected local storage behavior
- save and re-save behavior for encrypted files
- safe external link allow/block behavior
- idle-timeout shutdown logic
- table creation, merge, split, row, and column operations
- native file replacement, read-only files, Unicode paths, failed commits, and malformed encrypted envelopes

## Rust storage integration (development)

The source now uses a small dependency-free Rust DLL for same-directory temporary-file writes and legacy encrypted-envelope structure validation. Document saves, recovery snapshots, configuration, and image output use this module. Python's established `cryptography` dependency still performs encryption and authentication; the existing file format is unchanged. A structural validation pass is not authentication.

Writes synchronize the temporary file before replacement and avoid truncating the previous file on pre-commit failure. Existing destination DACL policy and protection status are copied to the empty temporary file before any bytes are written; a security-copy error fails closed. New files inherit the trusted parent directory policy. Owner, audit settings, integrity labels, alternate streams, and other metadata are not preserved. This is not a guarantee against power loss, malicious concurrent filesystem changes, or forensic recovery. Parents must already exist and be trusted. Native error codes propagate to the caller. Tab-close saves no longer retain passwords in document state.

This is a storage-safety change, not a measured performance improvement. Background workers, streaming encryption, native DPAPI migration, and word-count optimization are not included. The checked-in 3.4 downloads remain the previously published builds and do not yet contain this development integration.

## Security Notes

- Encryption is performed locally on the device
- The app does not require user accounts or network services
- Passwords are not persisted as part of a remote authentication system or retained in document state after use
- Integrity validation is built into the encrypted file format
- Recovery snapshots are encrypted and their local recovery key is protected with Windows DPAPI on Windows systems
- Sensitive local metadata files are hardened to the current user where supported by the host OS
- “Clear Editor Contents” removes text from the current session but should not be treated as a guaranteed forensic memory wipe

This project is designed to reduce exposure by keeping note creation, encryption, and storage on the user-controlled machine.

## Ideal Portfolio Talking Points

If you are presenting this project in a CV, portfolio, or interview, the strongest angles are:

- Built a secure local-first desktop application instead of a basic CRUD app
- Implemented encrypted storage and integrity validation for user documents
- Designed user-facing security features without sacrificing usability
- Packaged the product into a distributable Windows desktop application
- Added automated tests around critical workflows and regression-prone logic

## Author

Developed by **Min Thuta Saw Naing (Eric)**.

Erica reflects a practical blend of software engineering, user experience, and security-minded product development.
