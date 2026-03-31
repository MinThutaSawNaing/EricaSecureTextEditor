# Erica Secure Text Editor

Erica Secure Text Editor is a Windows desktop application for writing, encrypting, and managing sensitive notes entirely on the local machine. It combines a rich-text editing workflow with file-level encryption, recovery safeguards, and packaged desktop delivery through PyQt6, PyInstaller, and Inno Setup.

This project is a strong portfolio example of applied desktop engineering: secure local data handling, UI development, state management, packaging, and automated test coverage in a single Python codebase.

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
- HMAC-SHA256 integrity checks to detect tampering or corruption
- Password prompt and password strength feedback during secure save flows
- Idle timeout with auto-lock style shutdown behavior
- Clipboard auto-clear for copied sensitive content
- Read-only protection applied to encrypted output files after save
- Encrypted recovery snapshots for unsaved work

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
- Inno Setup script for creating an installer
- Application icon and packaged UI assets included in the repo

## Tech Stack

- Python 3
- PyQt6
- cryptography
- PyInstaller
- Inno Setup
- unittest

## Architecture Highlights

The application is implemented in a single primary desktop entrypoint, [`erica_secure_text_editor.py`](/d:/D/my%20software/Version3.0/erica_secure_text_editor.py), which combines:

- encryption and decryption utilities
- configuration and session persistence
- secure recovery snapshot handling
- rich-text editor actions
- multi-tab document management
- Windows-oriented desktop packaging support

Supporting project files:

- [`erica_secure_text_editor.spec`](/d:/D/my%20software/Version3.0/erica_secure_text_editor.spec) for executable builds
- [`erica_secure_text_editor.iss`](/d:/D/my%20software/Version3.0/erica_secure_text_editor.iss) for installer creation
- [`test_erica_secure_text_editor.py`](/d:/D/my%20software/Version3.0/test_erica_secure_text_editor.py) for automated verification

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the application

```bash
python erica_secure_text_editor.py
```

## Build for Windows

### Create the executable

```bash
pyinstaller erica_secure_text_editor.spec
```

The generated executable is placed in `dist/`.

### Create the installer

Use the included Inno Setup script:

[`erica_secure_text_editor.iss`](/d:/D/my%20software/Version3.0/erica_secure_text_editor.iss)

## Run Tests

```bash
python -m unittest test_erica_secure_text_editor.py
```

Current automated coverage includes:

- encryption and decryption roundtrip behavior
- recent files and last-session persistence
- encrypted recovery snapshot creation and restore validation
- save and re-save behavior for encrypted files
- idle-timeout shutdown logic
- table creation, merge, split, row, and column operations

## Security Notes

- Encryption is performed locally on the device
- The app does not require user accounts or network services
- Passwords are not persisted as part of a remote authentication system
- Integrity validation is built into the encrypted file format

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
