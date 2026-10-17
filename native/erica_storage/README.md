# erica_storage (storage ABI 1, organization ABI 2)

Rust `cdylib` for Windows with storage ABI 1 and organization ABI 2. The existing
storage exports below retain their behavior; the additive organization exports
implement token validation, authenticated encryption, DPAPI and guarded file I/O.
`rlib` output supports Rust tests. Organization operations require the dependencies
documented below; legacy password cryptography is not changed by this crate.

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
cargo fetch --locked --manifest-path native/erica_storage/Cargo.toml
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

## Organization C ABI (version 2)

```c
uint32_t erica_organization_abi_version(void); /* 2; storage ABI remains 1 */
uint32_t erica_org_call(uint32_t op, const uint8_t *input, size_t len,
                        uint8_t **out, size_t *out_len);
void erica_org_free(uint8_t *out, size_t len);
```

Use the C calling convention (`ctypes.CDLL`), `c_uint32` operation/status and
`c_size_t` byte lengths. All fields are bytes, with no terminators. A **pair** is
32 ASCII decimal digits: token1 then token2, exactly 16 digits each, distinct,
without trimming/coercion/reordering. Check values are exactly 5 ASCII decimal
digits (0-9), including leading zeroes. Old 12-character hexadecimal checks are
rejected. Path fields are strict UTF-8 absolute paths, without embedded NUL.

| op | Input | Success output |
|---:|---|---|
| 1 | pair32 | same pair32 |
| 2 | token16 | check5 |
| 3 | pair32 + check1:5 + check2:5 (42 bytes total) | pair32 |
| 4 | empty | random pair32 |
| 5 | arbitrary bytes | one byte 0 or 1: starts with `ERICAORG` |
| 6 | pair32 + plaintext bytes | organization envelope |
| 7 | pair32 + envelope bytes | authenticated plaintext bytes |
| 8 | pair32 | canonical base64 ASCII current-user DPAPI ciphertext |
| 9 | canonical base64 ASCII DPAPI ciphertext | validated pair32 |
| 10 | byte0 + path, or byte1 + pair32 + path | empty; destination verified |
| 11 | path | byte0 or byte1, from first 8 file bytes |
| 12 | pair32 + path byte length:u32LE + path + plaintext | empty; atomic read-only write |
| 13 | pair32 + path | authenticated file plaintext |

Statuses: 0 success; 1 invalid tokens/checks/input/path/base64/protected payload;
2 invalid/truncated/unsupported organization envelope; 3 authentication failure
(wrong tokens, order or modified authenticated bytes); 4 DPAPI failure; 5 system
or RNG failure; 6 destination encryption mode mismatch; 7 filesystem I/O failure;
1359 caught unwinding panic. No OS error details or sensitive data cross errors.
Malformed base64/payload is status1; DPAPI rejecting a corrupted blob is status4.
File classification of a missing file returns7, not password mode. Data format
classification recognizes the full magic even with missing/unsupported versions,
preventing silent legacy fallback; it is not structural validation/authentication.

Input must fit `ISIZE_MAX`, be readable, live and immutable for the synchronous
call; null input is accepted only for len0. The caller supplies two **distinct,
aligned, writable** output slots (pointer and size_t), not overlapping input.
Each valid slot is reset to null/zero before validation, and failures return no
owned buffer. Successful empty results use null/zero. Nonempty results are a
Rust-owned boxed byte slice: copy before calling `erica_org_free` exactly once
with the exact returned pointer/length. Free wipes that slice before releasing
it. Never free a foreign pointer, a modified length, a slice, or an already-freed
allocation. Free(null,0) is safe. Invalid null/size/alignment/overlap is rejected;
arbitrary pointer validity/lifetime cannot be checked. Pointer misuse, access
violations, aborts and OOM termination are outside catch_unwind guarantees.
All three exports contain unwinding panics.

### Compatibility, dependencies and secret lifetime

The version1 format is unchanged from the former Python implementation:
`ERICAORG | version:u8=1 | salt:16 | nonce:12 | ciphertext | GCM tag:16`.
The entire 37-byte header is AAD. Scrypt uses N=32768, r=8, p=1, output32 with
password `b"ERICAORG\0TOKENS\x01" + pair32`; AES-256-GCM uses a 12-byte nonce.
Fresh salt/nonce come from Windows `BCryptGenRandom` (system preferred RNG).
Decimal token generation rejects bytes >=250 before modulo10; duplicate pairs
regenerate token2. Leading zeroes and order are preserved. For a check, compute
`SHA256(b"ERICAORG\0CHECK\x01" + token16)`, interpret its first 8 bytes as an
unsigned big-endian u64, take modulo 100000, then format as exactly 5 zero-padded
ASCII decimal digits. For example, token `0123456789012345` gives `03129` and
token `9876543210987654` gives `77252`; token `0000000000000006` gives `05553`.
Checks are public approximately 17-bit typo checks, **not authentication**:
collisions are possible (about 1 in 100000 for independent random checks), and
publishing a check permits fast offline guesses of weak tokens. Use randomly
generated tokens.

Organization ABI 2 changes only the check wire format for op2/op3; callers must
reject organization ABI 1 DLLs and rebuild. Storage ABI stays 1. Old 12-character
hexadecimal checks must be regenerated from the same tokens and backups updated;
the shorter checks have weaker typo detection than the old 48-bit checks, but
the tokens, KDF, version1 encrypted file bytes, and DPAPI payload are unchanged.
Existing encrypted files and current-user protected token blobs need no migration.

DPAPI uses typed Windows `CryptProtectData`/`CryptUnprotectData` FFI with only
`CRYPTPROTECT_UI_FORBIDDEN` (no LOCAL_MACHINE flag), no optional entropy, and the
old payload `b"ERICAORG-TOKENS\x01" + pair32`. Thus prior same-user Python DPAPI
blobs remain readable. Strict canonical RFC4648 base64 is encoding only; DPAPI
failure/non-Windows builds never fall back to plaintext or machine protection.
Output from DPAPI is wiped before `LocalFree` using pointer-width-correct FFI.

Cargo.toml explicitly adds RustCrypto `aes-gcm = 0.10.3` (exact), `scrypt = 0.11`,
`sha2 = 0.10`, `zeroize = 1`, and `base64 = 0.22`. No bespoke AES or scrypt is
implemented. Direct `aes = 0.8`, `ghash = 0.5`, and `polyval = 0.6` dependencies
enable upstream zeroize features through feature unification; aes-gcm's zeroize
feature is also enabled. `subtle = 2` supplies constant-time equality for fixed
length checks/token comparison. Unneeded default OS RNG/password-hash features are off.
Cargo.lock records all resolved versions/checksums; initial network access is
required by `cargo fetch --locked`, then builds/tests work offline and locked.
Primary API references: <https://docs.rs/aes-gcm/0.10.3/aes_gcm/>,
<https://docs.rs/scrypt/0.11.0/scrypt/>, <https://docs.rs/zeroize/1/zeroize/>.

Application-owned temporary key/password/plaintext/token buffers use Zeroizing;
failed authentication never returns plaintext. Key schedule/hash wiping features
reduce residual state, but this is **not a complete process-memory erasure
guarantee**: upstream scrypt scratch allocations/internal crypto copies, registers,
allocator/OS copies, caller input, Python strings and the caller's copied result
are not all under this module's control. Keep secrets short-lived, do not log or
persist plaintext tokens, and do not claim they cannot appear in process dumps.

### Guarded I/O trust boundary

Op10 allows a missing/zero-length regular destination in either mode. Otherwise
magic must match the selected mode; organization destinations must authenticate
with the provided ordered pair before overwrite. Password mode's legacy contents
are unchanged. Op12 runs this guard before crypto and again immediately before
the existing native atomic writer commits; it writes encrypted data only and
requests read-only. DACL preservation, cleanup, attribute restoration and atomic
replacement are inherited from the existing writer above. The guard never
silently converts password to organization or vice versa. Existing nonempty
unsupported organization envelopes fail closed even if they have the magic.

These checks do not provide adversarial filesystem race resistance. All path
operations require a stable trusted parent/ancestors and caller serialization;
another actor replacing a file between verification/commit remains outside the
guarantee. Symlink/non-file destinations are rejected by destination verification,
and the native writer rejects reparse-point destinations per its existing model.

Organization Rust tests cover strict tokens/checks/order, a captured old Python
v1 fixture in both directions, tampered header/ciphertext/tag, empty/binary data,
rejection sampling and duplicate rejection, invalid FFI/wire inputs, output
ownership, Windows DPAPI/RNG, mode guards, UTF-8 paths, native read-only atomic
replacements, old-byte preservation on mismatch/wrong tokens and temp cleanup.