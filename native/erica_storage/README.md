# erica_storage (ABI 1)

Dependency-free Rust `cdylib` for Windows. No DPAPI, encryption, authentication,
or Python integration is implemented here. `rlib` output supports Rust tests.

## C ABI

```c
#include <stddef.h>
#include <stdint.h>
uint32_t erica_storage_abi_version(void); /* 1 */
size_t erica_count_words_utf16(const uint16_t *text, size_t len);
int32_t erica_validate_encrypted(const uint8_t *data, size_t len);
uint32_t erica_atomic_write(const uint16_t *path, size_t path_len,
                           const uint8_t *data, size_t data_len,
                           int32_t read_only);
```

Use C calling convention (`ctypes.CDLL`, not `WinDLL`), `c_size_t` lengths,
`c_uint32` status, `c_int32` flag/result, and a UTF-16 buffer. Path length is in
UTF-16 code units, not bytes or Unicode characters; exclude any terminating NUL.
The caller supplies an absolute Windows path. Empty, relative, drive-relative,
embedded-NUL paths and flags other than 0/1 return 87. Buffers must remain live
and unmodified throughout the synchronous call. Nonempty buffers must be valid;
null data is allowed only for a zero-byte write. Pointer validity cannot be
verified by this ABI. Invalid pointers or concurrent mutation are undefined
behavior, not catchable Rust panics.

Validation returns 0 only when the non-null buffer's length fits
salt(16) + IV(16) + ciphertext(at least 16, aligned to 16) + tag(32): minimum 80.
Otherwise it returns 1. **This checks layout only, not authenticity**, and need
not read the supplied bytes. Atomic write does not implicitly validate layout;
it accepts arbitrary bytes, including empty content.

Writes return 0 on success, otherwise a Win32 error code, e.g. 87 invalid
parameter, 5 access denied, 3 path not found, 32 sharing violation. Unwinding
Rust panics map to 1359 (internal error), RNG failure to 31 (general failure),
and exhausted random-name retries to 80. No NTSTATUS is exposed. Non-Windows
builds support validation but return 50 for otherwise well-formed writes.

## UTF-16 word counting (additive ABI 1 export)

`erica_count_words_utf16` returns `size_t` (`ctypes.c_size_t`), matching Python
`len(text.split())`: count runs of non-whitespace without allocating word lists.
It scans once in O(len) time and O(1) native memory, suitable for changed Qt text
blocks. Length is UTF-16 **code units**, excluding any terminator. Embedded NUL
is ordinary non-whitespace. All Python whitespace is recognized: U+0009–000D,
U+001C–0020 (including the four Python-specific control separators), U+0085,
U+00A0 (NBSP), U+1680, U+2000–200A, U+2028–2029, U+202F, U+205F, U+3000.
Zero-width space, BOM, and U+180E are not separators. All separators are BMP;
surrogate pairs and lone surrogates are non-whitespace and need no decoding.

Zero length returns zero without accessing the pointer (null allowed). Null
nonempty pointers, misaligned pointers, lengths above `ISIZE_MAX / 2`, and caught
unwinding panics return zero as well; there is no separate error status. Otherwise
the caller must provide aligned, readable storage, live and unmodified for the
call. Pointer validity cannot be verified; access violations are not caught.
The export is additive: existing exports and ABI version **1** are unchanged.

Python `erica_storage.count_words(text)` accepts only `str`, encodes UTF-16LE
with `surrogatepass`, and copies into a live `ctypes.c_uint16` array. The binding
uses no private CPython string representation and preserves NUL/lone surrogates.
The copy/encoding costs O(len) memory; native scanning allocates nothing. Rebuild
older ABI-1 DLLs to provide this new symbol before using the updated binding.
No main-app or Qt integration is performed here.

## Filesystem scope and failure behavior

- **Trusted, stable parent directory required.** Caller must control the entire
  path/ancestor chain and serialize destination operations. Ancestor junctions,
  mount points, network paths, device namespaces and hostile path races are not
  sandboxed. Use ordinary absolute paths on a local Windows filesystem with
  atomic rename support. Long-path behavior follows Windows configuration.
- The destination itself is checked with `symlink_metadata`, twice, and rejected
  if a directory or any reparse point (including symlinks). This does not close
  TOCTOU races against an adversary who can mutate the directory.
- A same-directory `.erica-<128-bit OS random>.tmp` is opened with `create_new`.
  BCryptGenRandom supplies randomness. `write_all` and `sync_all` complete before
  closing the handle and committing with
  `MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`. No fallback truncates or writes
  the old destination in place.
- Requested read-only state is applied to the temp before commit. An existing
  read-only destination has its attribute cleared only immediately before the
  move. A failed commit restores its original attributes; an unwind also attempts
  restoration. If restoration itself fails, its error is returned (with one
  best-effort retry on guard drop), and attributes may remain changed. Old file
  bytes are not rewritten. A successful replacement's attributes come from temp.
- Temp cleanup is RAII and retains a handle with DELETE/write-attribute rights
  acquired before DACL restriction, so a copied DACL denying subsequent opens
  does not block cleanup or require ACL widening. It removes read-only temps on normal errors and
  unwinding. Cleanup is best effort: process termination, power loss, permission
  changes or filesystem failures can leave a temp behind. A hard crash between
  attribute clearing and commit can leave old attributes writable. No absolute
  power-loss/directory durability guarantee is claimed.
- **Existing destination DACL and its protection status are preserved.** Before
  writing any data, `GetFileSecurityW` reads the old DACL into a DWORD-aligned
  descriptor and `GetSecurityDescriptorControl` determines protection status.
  `SetFileSecurityW` applies the DACL and explicit protected/unprotected status
  to the still-empty temp. Any security API failure aborts before writing bytes
  or modifying the old file. Copying requires READ_CONTROL on the old file and
  WRITE_DAC on temp; unavailable rights fail closed with the Windows error.
  Windows can normalize auto-inheritance provenance flags; preservation means
  equivalent access policy and the same DACL protection status, not byte-identical
  security descriptors. New files inherit the trusted parent's policy. Existing
  owner/group, SACL/audit settings, integrity labels, streams, timestamps, identity
  and hard links are not preserved. DACL preservation does not provide race
  resistance: caller serialization and stable trusted ancestors remain required.
  Read-only is an attribute, not an access-control boundary.
- Panics are caught at exported seams; access violations, aborts, OOM termination,
  and foreign exceptions are not recoverable by `catch_unwind`.

## Build and test

From repository root on Windows with the Rust MSVC toolchain and Windows SDK:

```text
cargo fmt --manifest-path native/erica_storage/Cargo.toml -- --check
cargo test --offline --locked --manifest-path native/erica_storage/Cargo.toml
cargo clippy --offline --locked --manifest-path native/erica_storage/Cargo.toml --all-targets -- -D warnings
cargo build --offline --locked --release --manifest-path native/erica_storage/Cargo.toml
```

Or run `./build_native.ps1` from the repository root to test, lint and build the
release DLL and copy it beside `erica_storage.py`. Then run
`python -m unittest test_native_wordcount test_erica_storage`. Word-count tests
cover every BMP unit in Rust, all Unicode code points against Python `str.split`,
all 29 whitespace characters, NUL, surrogate pairs/lone surrogates, randomized
mixed text, large blocks, and invalid FFI arguments.

The release artifact is `erica_storage.dll` in Cargo's release target directory
(which may be overridden by repository/environment Cargo configuration). Tests
cover layout boundaries, argument errors, Unicode, new/empty writes, read-only
replacement, blocked rename preserving bytes, private internal deterministic
commit failure and panic injection, cleanup and path errors. Windows ACL tests
use `icacls`, `whoami`, and PowerShell `Get-Acl` to check protected and inherited
DACL policy/protection equivalence and security-copy failure before data writes.
The symlink test
skips creation only when Windows denies the symlink privilege (1314). Injection
has no exported ABI or runtime configuration.