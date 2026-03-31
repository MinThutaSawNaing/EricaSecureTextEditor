# Erica Secure Text Editor

Windows-first encrypted text editing with a lightweight desktop workflow, local-only storage, and a no-nonsense PyQt interface.

## Why It Hits

Erica is built for people who want to write sensitive notes without shipping their text to a cloud service. Everything happens locally. You write, encrypt, save, and close. No accounts. No sync drama. No backend attack surface.

## Features

- AES-256 encryption for saved documents
- HMAC-SHA256 integrity validation to detect tampering
- Read-only encrypted files after save
- Clipboard auto-clear timer
- Idle timeout / auto-lock behavior
- Password strength meter
- Rich-text editing with tabs, lists, links, and zoom controls
- Windows-focused packaging with PyInstaller

## Platform

This project now targets **Windows only**.

The primary application entrypoint is:

- `Erica_Secure_Text_Editor_Update30.py`

The `Erica_Secure_Text_Editor_Update30_Linux.py` file is kept in the repo as a legacy snapshot, but the app is no longer supported on Linux or macOS.

## Quick Start

1. Install Python 3.11+ on Windows.
2. Install dependencies:

```bash
pip install PyQt6 cryptography
```

3. Run the app:

```bash
python Erica_Secure_Text_Editor_Update30.py
```

## Build EXE

Use the included PyInstaller spec:

```bash
pyinstaller Erica_Secure_Text_Editor_Update30.spec
```

The generated executable will be placed in `dist/`.

## Project Files

- `Erica_Secure_Text_Editor_Update30.py`: main Windows app
- `Erica_Secure_Text_Editor_Update30.spec`: PyInstaller build config
- `icon.ico`: Windows app icon
- `closebutton.png`: UI asset
- `final.iss`: installer-related script

## Security Notes

- Encryption happens locally on the device.
- Passwords are not stored by the app.
- Encrypted files are written to disk and then marked read-only.
- Integrity validation helps catch corrupted or modified encrypted files.

## Recent Maintenance

Recent fixes included:

- safer Windows config-path handling
- correct plain-text handling for content containing `<` and `>`
- reliable re-save behavior for previously locked encrypted files
- tighter encryption/decryption context handling

## Author

Developed by **Min Thuta Saw Naing (Eric)**.

If you want Erica to feel sharper, safer, and faster with each release, this repo is now set up for that next phase.
