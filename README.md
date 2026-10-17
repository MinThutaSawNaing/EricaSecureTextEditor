# Erica Secure Text Editor

A local-first Windows desktop editor for encrypted notes and rich-text documents.
Erica combines tabbed editing, password or shared organization-token protection,
encrypted image files, and local workspace recovery. The interface uses Python
and PyQt6; Rust provides organization security, native storage, and word counting.

## Download 3.6

**Windows x64.** Packaged builds do not require Python or Rust to be installed.

| Download | Purpose |
| --- | --- |
| [Windows installer](./release/EricaSecureTextEditorSetup_3.6.exe?raw=true) | Recommended installation and upgrades |
| [Standalone executable](./release/EricaSecureTextEditor.exe?raw=true) | Run without installation |
| [SHA-256 checksums](./release/SHA256SUMS.txt?raw=true) | Check the downloaded artifacts |

The [`release/`](./release/) folder contains only the current release. See
[release notes and artifact details](./release/README.md); older binaries remain
in Git history, not in the current download folder.

The installer defaults to the current user, with an optional all-users install.
It creates a Start Menu shortcut, offers a desktop shortcut, and registers
`.erica` in **Open with** without changing the default app. Upgrades retain the
existing installation scope and directory.

**Unsigned software:** Windows may display an unknown-publisher warning. Verify
the source and download location before running. Checksums detect changed bytes;
they do not authenticate the publisher or replace a digital signature.

## What's new in 3.6

- Rust-backed organization-token encryption and Windows-protected token storage.
- A compact, theme-aware setup dialog with explicit 16-digit input warnings.
- Automatically generated, read-only five-digit checks with optional Copy buttons.
- Newly generated tokens are shown immediately, with a screen-privacy reminder.
- Existing password files and the organization version-1 file format remain compatible.

## Features

- Multiple tabs, rich text, links, lists, tables, undo/redo, and zoom.
- Right-click **Font**, **Paragraph**, and **Table** menus for editing controls.
- Password-protected `.erica` documents; legacy password `.enc` files are supported.
- Shared organization-token mode for documents and encrypted `.eimg` images.
- Recent files, session reopening, light/dark themes, and incremental word counts.
- Background encryption, storage, and periodic encrypted recovery snapshots.

## Get started

### Password-protected documents

1. Install Erica or launch the standalone executable.
2. Choose **File > New** (`Ctrl+N`) and write your document.
3. Under **Security > Mode for New Files**, select **Password Mode**.
4. Choose **File > Save Encrypted** (`Ctrl+S`), select a filename, and enter a
   strong, unique password. New documents use `.erica`.
5. Use **File > Open Encrypted** (`Ctrl+O`) to reopen a document with its password.

Keep passwords in a trusted password manager. There is no password-reset service
or decryption backdoor. Recovery snapshots are not a substitute for file backups.

### Organization-token setup

Organization mode is **software shared-key encryption, not a hardware HSM**.
It needs no hardware device or external provisioning service. Each authorized
Windows account must be configured with the same two tokens in the same order.

1. Open **Security > Configure Organization Tokens**.
2. For a new organization, choose **Generate a new organization token pair**.
   Each token must contain exactly **16 ASCII digits (`0–9`)**. The tokens must
   differ; leading zeros and token order are significant.
3. Generated tokens are shown automatically and **Show tokens** is checked.
   Generate only on a private screen; uncheck it to hide the tokens. Manually
   entered tokens are hidden by default and can also be shown with this control.
4. Erica generates an exactly **five-digit** check for each valid token in Rust.
   Checks are read-only and preserve leading zeros; do not enter checks manually.
   Invalid input displays an inline warning, clears the check, and disables Copy.
5. Back up both ordered tokens and their checks in approved secret storage.
   **Copy** beside a check is optional and copies only that check, not the token.
   Clipboard history or synchronization may retain it. Keep checks private too.
6. On another authorized account, enter the original pair and compare the generated
   checks against the trusted backup. **Do not generate a new pair to join an
   existing organization.** Distribute tokens over a secure channel, not with files.
7. Confirm **I have securely backed up both tokens and checks**, then choose
   **Save**. Successful setup selects Organization Token Mode. Changing either
   token updates its check and resets the backup confirmation.

Save and open files normally after enrollment. Matching organization files open
without per-file password prompts. Password files still request their passwords,
regardless of the selected mode for new files.

### Switching modes and handling images

- **Security > Mode for New Files** controls new files and **Save As Encrypted**.
  A normal save, including a tab-close save, retains a file's existing protection.
- To convert an open document, select the desired mode and use **File > Save As
  Encrypted** (`Ctrl+Shift+S`) with a **new filename**. Cross-mode overwrites and
  organization overwrites using a different token pair are refused.
- **File > Encrypt Image** creates an encrypted `.eimg` file using the selected
  mode. **File > Decrypt Image** writes a decrypted image; protect that output.
- **Security > Remove Local Organization Tokens** removes local enrollment and
  returns new files to Password Mode. It does not revoke tokens elsewhere.

## Security model and limitations

### Encryption and compatibility

| Protection | Implementation |
| --- | --- |
| Password files | AES-256-CBC with PKCS#7 padding and HMAC-SHA256 over salt, IV, and ciphertext; PBKDF2-HMAC-SHA256, 100,000 iterations, 32-byte key |
| Organization files | AES-256-GCM; scrypt (`N=32768`, `r=8`, `p=1`, 32-byte key) over the domain-separated, ordered token pair |

Password encryption uses a fresh 16-byte salt and 16-byte IV; authentication is
checked before decryption. Organization encryption uses a fresh 16-byte salt and
12-byte nonce. Its `ERICAORG` version-1 envelope authenticates the complete header
and includes a 16-byte GCM tag. Tokens and checks are not stored in that header.

The Rust migration preserves organization ciphertext and DPAPI token-blob formats;
existing files do not need rewriting. Older password-only Erica builds cannot
open organization files. Password encryption and its legacy format are unchanged.

If upgrading from source builds with 12-character hexadecimal checks, regenerate
the new five-digit checks from the **same tokens** and update enrollment backups.
Rebuild the DLL: organization ABI is now 2; storage ABI remains 1.

- Anyone with both tokens can decrypt files protected by that pair. There is no
  per-user identity, hardware isolation, audit trail, or remote revocation.
- Lost tokens cannot be recovered by Erica. Replacing tokens does not re-encrypt
  existing files; retain old pairs until files have been deliberately migrated.
- Five-digit checks are short typo checks, **not authentication or standard HSM
  key check values**. Collisions are possible: different tokens can share a check.
- Checks are derived directly from individual tokens and allow fast offline guess
  testing. Do not publish them or store them alongside distributed documents.
  Use generated random tokens, not dates, repeated digits, or other patterns.
- Two random 16-digit decimal tokens provide about 106 bits of combined input
  entropy before disclosure; AES-256 does not make them 256-bit secrets.

### Local storage and recovery

Organization tokens are encrypted with **Windows DPAPI for the current user** in
`%APPDATA%\SecureText\config.json`; check values are not persisted there. There is
no plaintext token-storage fallback. Copying config files to another account or
PC is not an enrollment method, and the standalone executable does not make
account-bound settings portable.

Unsaved work is periodically stored in `recovery.enc`, encrypted with a separate
local recovery key protected by current-user DPAPI. A startup prompt offers to
restore a usable snapshot. Account/profile loss or loss of the protected key may
make recovery unavailable. Back up encrypted documents and credentials separately.

Recovery is tied to the Windows account, **not** the document password or token
pair. Removing tokens does not erase decrypted tabs or their recovery snapshots.
Software running as the signed-in user may be able to unprotect local keys and
tokens. Decrypted content also exists in memory; Python strings and bytes cannot
be reliably forensically erased.

Idle shutdown, clipboard clearing, file permissions, and read-only attributes are
convenience safeguards, not a security boundary. Organization files can reopen
without a password after idle shutdown. **Lock your Windows session** when away;
clipboard history, malware, screenshots, and a compromised account remain risks.

This project has not undergone an independent security audit. It does not claim
FIPS validation, hardware-backed key custody, or enterprise identity enforcement.

## Run from source

Use **64-bit Windows**, **Python 3.10+**, a stable **Rust MSVC x64 toolchain**,
and **Visual Studio C++ Build Tools with a Windows SDK**. Install these tools
before building. Run the following in PowerShell from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\build_native.ps1 -FetchDependencies
python erica_secure_text_editor.py
```

The first native build fetches dependencies pinned by `Cargo.lock`, runs native
tests and Clippy when available, and installs the release DLL beside the source.
Later builds can omit `-FetchDependencies` and work offline. Rebuild after native
changes. The DLL is required; there is no silent Python fallback for native
storage or organization security.

### Tests

After building the DLL, run the Python suite without opening UI windows:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -B -m unittest discover -s . -p 'test_*.py' -v
Remove-Item Env:QT_QPA_PLATFORM
```

`build_native.ps1` runs native tests in the normal debug profile. For faster
cryptographic test execution after compilation, optionally run
`cargo test --release --manifest-path native/erica_storage/Cargo.toml --offline --locked`.

### Package Windows builds

Install PyInstaller in the Python environment and Inno Setup 6 separately. Use
your **actual installed compiler path**; `-IsccExe` overrides the script default:

```powershell
python -m pip install pyinstaller
.\build_windows.ps1 -IsccExe 'C:\path\to\Inno Setup 6\ISCC.exe'
```

The script tests/builds the native DLL, runs Python tests, packages the executable
and installer, copies matching installer source, and writes `release/SHA256SUMS.txt`.
It keeps only the current installer and removes successful temporary staging and
duplicate executable output. It does not install dependencies, run the installer,
sign binaries, upload artifacts, or push Git changes.

## Source layout

- [`erica_secure_text_editor.py`](./erica_secure_text_editor.py): desktop entry
  point, document workflows, password encryption, and recovery encryption.
- [`erica_organization.py`](./erica_organization.py) and
  [`erica_organization_ui.py`](./erica_organization_ui.py): native API adapter and setup UI.
- [`native/erica_storage/`](./native/erica_storage/): Rust organization validation,
  generation, checks, crypto, DPAPI, organization I/O, atomic storage, and word counts.
- `erica_formatting.py`, `erica_tables.py`, `erica_tasks.py`, and
  `erica_wordcount.py`: editing controls, background workers, and count integration.

## License

[MIT License](./LICENSE). Copyright © 2026 Min Thuta Saw Naing Eric.