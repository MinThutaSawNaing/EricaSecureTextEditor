//! Windows atomic storage and legacy encrypted-envelope layout validation.
//! See README.md for the trust model and ABI contract. No cryptographic authentication
//! is performed here. All exported functions contain Rust unwinding panics.

use std::panic::{catch_unwind, AssertUnwindSafe};

mod organization;

const ERROR_INVALID_PARAMETER: u32 = 87;
const ERROR_INTERNAL_ERROR: u32 = 1359;
#[cfg(not(windows))]
const ERROR_NOT_SUPPORTED: u32 = 50;

/// Return ABI version 1.
#[no_mangle]
pub extern "C" fn erica_storage_abi_version() -> u32 {
    catch_unwind(|| 1).unwrap_or(1)
}

// Python str.isspace()/str.split() includes U+001C..U+001F in addition to
// Unicode White_Space. All separators are BMP, so decoding surrogate pairs is
// unnecessary: paired and unpaired surrogates are always non-whitespace.
fn python_whitespace(unit: u16) -> bool {
    matches!(unit, 0x0009..=0x000d | 0x001c..=0x0020 | 0x0085 | 0x00a0 |
        0x1680 | 0x2000..=0x200a | 0x2028..=0x2029 | 0x202f | 0x205f | 0x3000)
}

/// Count nonempty whitespace-delimited words, like Python `len(text.split())`.
/// Length is in UTF-16 code units; embedded NUL and unpaired surrogates are text.
/// Returns zero for empty input, invalid arguments, or a caught Rust panic.
///
/// # Safety
/// For nonempty input, `text` must point to an aligned, readable allocation of
/// `len` u16 units, live and unmodified for this call. Null, misalignment and
/// excessive lengths are rejected; arbitrary invalid pointers cannot be detected.
#[no_mangle]
pub unsafe extern "C" fn erica_count_words_utf16(text: *const u16, len: usize) -> usize {
    catch_unwind(|| {
        if len == 0
            || text.is_null()
            || len > isize::MAX as usize / 2
            || !(text as usize).is_multiple_of(std::mem::align_of::<u16>())
        {
            return 0;
        }
        // SAFETY: caller guarantees readable storage; bounds/alignment checked above.
        let units = unsafe { std::slice::from_raw_parts(text, len) };
        let mut count = 0;
        let mut in_word = false;
        for &unit in units {
            let nonspace = !python_whitespace(unit);
            count += usize::from(nonspace && !in_word);
            in_word = nonspace;
        }
        count
    })
    .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn word_count_whitespace_exhaustive_bmp() {
        let whitespace: Vec<u16> = (0..=u16::MAX)
            .filter(|&unit| {
                char::from_u32(u32::from(unit)).is_some_and(char::is_whitespace)
                    || (0x1c..=0x1f).contains(&unit)
            })
            .collect();
        assert_eq!(whitespace.len(), 29);
        for unit in 0..=u16::MAX {
            let text = [b'a' as u16, unit, b'b' as u16];
            // SAFETY: text is a live aligned array of three units.
            assert_eq!(
                unsafe { erica_count_words_utf16(text.as_ptr(), text.len()) },
                if whitespace.contains(&unit) { 2 } else { 1 },
                "U+{unit:04X}"
            );
        }
    }

    #[test]
    fn word_count_unicode_and_boundaries() {
        for (text, expected) in [
            ("", 0),
            (" \t\r\n", 0),
            ("one", 1),
            ("  one  two\nthree ", 3),
            ("မြန်မာ 日本語 😀\u{a0}🔒", 4),
            ("a\0b\u{200b}c\u{feff}d", 1),
        ] {
            let units: Vec<u16> = text.encode_utf16().collect();
            // SAFETY: units is live and aligned, including the empty case.
            assert_eq!(
                unsafe { erica_count_words_utf16(units.as_ptr(), units.len()) },
                expected
            );
        }
        let units = [0xd800, 0x20, 0xdc00, 0xd800, 0xdc00, 0x1c, 0xdfff];
        // SAFETY: units is live and aligned; ill-formed UTF-16 is accepted.
        assert_eq!(
            unsafe { erica_count_words_utf16(units.as_ptr(), units.len()) },
            3
        );
    }

    #[test]
    fn word_count_invalid_arguments() {
        let units = [0u16];
        // SAFETY: all invalid pointers/lengths are rejected before dereferencing.
        unsafe {
            assert_eq!(erica_count_words_utf16(std::ptr::null(), 0), 0);
            assert_eq!(erica_count_words_utf16(std::ptr::null(), 1), 0);
            assert_eq!(erica_count_words_utf16(units.as_ptr(), usize::MAX), 0);
            assert_eq!(
                erica_count_words_utf16(units.as_ptr(), isize::MAX as usize / 2 + 1),
                0
            );
            assert_eq!(
                erica_count_words_utf16(units.as_ptr().cast::<u8>().add(1).cast(), 1),
                0
            );
        }
    }

    #[test]
    fn legacy_layout_lengths_and_abi() {
        assert_eq!(erica_storage_abi_version(), 1);
        let bytes = [0u8; 256];
        for len in 0..=256 {
            let expected = if len >= 80 && (len - 64) % 16 == 0 {
                0
            } else {
                1
            };
            // SAFETY: buffer holds all tested lengths.
            assert_eq!(
                unsafe { erica_validate_encrypted(bytes.as_ptr(), len) },
                expected
            );
        }
        // SAFETY: null is explicitly rejected before any access.
        assert_eq!(unsafe { erica_validate_encrypted(std::ptr::null(), 80) }, 1);
        assert!(!valid_layout_len(usize::MAX));
    }

    #[test]
    fn invalid_ffi_arguments() {
        let path: Vec<u16> = "C:\\file".encode_utf16().collect();
        let nul = [b'C' as u16, 0];
        // SAFETY: buffers are valid; deliberately invalid counts/null are checked first.
        unsafe {
            assert_eq!(
                erica_atomic_write(std::ptr::null(), 0, std::ptr::null(), 0, 0),
                87
            );
            assert_eq!(
                erica_atomic_write(path.as_ptr(), 0, std::ptr::null(), 0, 0),
                87
            );
            assert_eq!(
                erica_atomic_write(path.as_ptr(), path.len(), std::ptr::null(), 1, 0),
                87
            );
            assert_eq!(
                erica_atomic_write(path.as_ptr(), path.len(), std::ptr::null(), 0, 2),
                87
            );
            assert_eq!(
                erica_atomic_write(nul.as_ptr(), nul.len(), std::ptr::null(), 0, 0),
                87
            );
            assert_eq!(
                erica_atomic_write(path.as_ptr(), usize::MAX, std::ptr::null(), 0, 0),
                87
            );
            assert_eq!(
                erica_atomic_write(
                    path.as_ptr(),
                    path.len(),
                    path.as_ptr().cast(),
                    usize::MAX,
                    0
                ),
                87
            );
        }
    }

    #[cfg(windows)]
    mod win {
        use super::*;
        use std::fs;
        use std::io;
        use std::os::windows::{ffi::OsStrExt, fs::OpenOptionsExt};
        use std::path::{Path, PathBuf};
        use std::sync::atomic::{AtomicU64, Ordering};

        struct TestDir(PathBuf);
        impl TestDir {
            fn new() -> Self {
                static NEXT: AtomicU64 = AtomicU64::new(0);
                let root = std::env::temp_dir();
                for _ in 0..100 {
                    let path = root.join(format!(
                        "erica-storage-test-{}-{}",
                        std::process::id(),
                        NEXT.fetch_add(1, Ordering::Relaxed)
                    ));
                    match fs::create_dir(&path) {
                        Ok(()) => return Self(path),
                        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
                        Err(e) => panic!("create test directory: {e}"),
                    }
                }
                panic!("test directory collisions")
            }
            fn assert_no_temps(&self) {
                for entry in fs::read_dir(&self.0).unwrap() {
                    assert!(!entry
                        .unwrap()
                        .file_name()
                        .to_string_lossy()
                        .starts_with(".erica-"));
                }
            }
        }
        impl Drop for TestDir {
            fn drop(&mut self) {
                for entry in fs::read_dir(&self.0).unwrap().flatten() {
                    if entry.path().is_file() {
                        let mut permissions = entry.metadata().unwrap().permissions();
                        #[allow(clippy::permissions_set_readonly_false)]
                        // Windows-only test cleanup.
                        permissions.set_readonly(false);
                        let _ = fs::set_permissions(entry.path(), permissions);
                    }
                }
                let _ = fs::remove_dir_all(&self.0);
            }
        }
        fn write(path: &Path, data: &[u8], readonly: bool) -> u32 {
            let wide: Vec<u16> = path.as_os_str().encode_wide().collect();
            // SAFETY: both buffers remain live and unmodified during the call.
            unsafe {
                erica_atomic_write(
                    wide.as_ptr(),
                    wide.len(),
                    data.as_ptr(),
                    data.len(),
                    i32::from(readonly),
                )
            }
        }

        #[test]
        fn new_unicode_empty_and_replacement() {
            let dir = TestDir::new();
            let path = dir.0.join("秘密-é-🔒.dat");
            assert_eq!(write(&path, b"first", false), 0);
            assert_eq!(fs::read(&path).unwrap(), b"first");
            assert_eq!(write(&path, b"second", true), 0);
            assert_eq!(fs::read(&path).unwrap(), b"second");
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            assert_eq!(write(&path, b"third", true), 0);
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            assert_eq!(write(&path, b"", false), 0);
            assert!(fs::read(&path).unwrap().is_empty());
            assert!(!fs::metadata(&path).unwrap().permissions().readonly());
            // Null with zero data length is allowed.
            let wide: Vec<u16> = path.as_os_str().encode_wide().collect();
            assert_eq!(
                unsafe { erica_atomic_write(wide.as_ptr(), wide.len(), std::ptr::null(), 0, 0) },
                0
            );
            dir.assert_no_temps();
        }

        #[test]
        fn injected_failure_restores_readonly_and_cleans_temp() {
            let dir = TestDir::new();
            let path = dir.0.join("old.dat");
            assert_eq!(write(&path, b"old", true), 0);
            let error = windows::atomic_write(&path, b"new", true, || {
                assert!(!fs::metadata(&path)?.permissions().readonly());
                Err(io::Error::from_raw_os_error(5))
            })
            .unwrap_err();
            assert_eq!(error.raw_os_error(), Some(5));
            assert_eq!(fs::read(&path).unwrap(), b"old");
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            dir.assert_no_temps();
        }

        fn acl_snapshot(path: &Path) -> String {
            let output = std::process::Command::new("powershell.exe")
                .args(["-NoProfile", "-NonInteractive", "-Command",
                    "$ErrorActionPreference='Stop'; $a=Get-Acl -LiteralPath $env:ERICA_TEST_ACL_PATH; $a.AreAccessRulesProtected; $a.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)"])
                .env("ERICA_TEST_ACL_PATH", path)
                .output().unwrap();
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            // Windows may clear SE_DACL_AUTO_INHERITED when copying a protected
            // DACL. It records provenance, not ACE access policy or protection.
            String::from_utf8(output.stdout)
                .unwrap()
                .replace("D:PAI", "D:P")
                .replace("D:AI", "D:")
        }

        #[test]
        fn protected_dacl_preserved_before_bytes_and_after_replace() {
            let dir = TestDir::new();
            let path = dir.0.join("restricted.dat");
            fs::write(&path, b"old").unwrap();
            let whoami = std::process::Command::new("whoami.exe").output().unwrap();
            assert!(whoami.status.success());
            let user = String::from_utf8(whoami.stdout).unwrap();
            let grant = format!("{}:(F)", user.trim());
            let output = std::process::Command::new("icacls.exe")
                .arg(&path)
                .args(["/inheritance:r", "/grant:r", &grant])
                .output()
                .unwrap();
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
            let before = acl_snapshot(&path);
            assert!(before.starts_with("True"), "{before}");
            windows::atomic_write_with_security(
                &path,
                b"new",
                false,
                |source, temp| {
                    assert_eq!(fs::metadata(temp)?.len(), 0);
                    windows::copy_dacl(source, temp)?;
                    assert_eq!(acl_snapshot(temp), before);
                    Ok(())
                },
                || Ok(()),
            )
            .unwrap();
            assert_eq!(fs::read(&path).unwrap(), b"new");
            assert_eq!(acl_snapshot(&path), before);
            // Exercise the actual exported path with the same restricted policy.
            assert_eq!(write(&path, b"third", false), 0);
            assert_eq!(acl_snapshot(&path), before);
            dir.assert_no_temps();

            // Even a copied DACL denying this writer data-write/delete rights
            // must not prevent rollback cleanup in the trusted parent directory.
            let read_grant = format!("{}:(R)", user.trim());
            assert!(std::process::Command::new("icacls.exe")
                .arg(&path)
                .args(["/grant:r", &read_grant])
                .output()
                .unwrap()
                .status
                .success());
            let restricted = acl_snapshot(&path);
            let error = windows::atomic_write(&path, b"uncommitted", false, || {
                Err(io::Error::from_raw_os_error(5))
            })
            .unwrap_err();
            assert_eq!(error.raw_os_error(), Some(5));
            assert_eq!(fs::read(&path).unwrap(), b"third");
            assert_eq!(acl_snapshot(&path), restricted);
            dir.assert_no_temps();
            // Owner retains implicit WRITE_DAC; restore rights for test teardown.
            assert!(std::process::Command::new("icacls.exe")
                .arg(&path)
                .args(["/grant:r", &grant])
                .output()
                .unwrap()
                .status
                .success());
        }

        #[test]
        fn unprotected_dacl_remains_equivalent() {
            let dir = TestDir::new();
            let path = dir.0.join("inherited.dat");
            fs::write(&path, b"old").unwrap();
            let before = acl_snapshot(&path);
            assert!(before.starts_with("False"), "{before}");
            assert_eq!(write(&path, b"new", false), 0);
            assert_eq!(acl_snapshot(&path), before);
            dir.assert_no_temps();
        }

        #[test]
        fn security_failure_is_closed_before_any_data_write() {
            let dir = TestDir::new();
            let path = dir.0.join("old.dat");
            assert_eq!(write(&path, b"old", true), 0);
            let before = acl_snapshot(&path);
            let error = windows::atomic_write_with_security(
                &path,
                b"secret new data",
                false,
                |source, temp| {
                    assert_eq!(source, path);
                    assert_eq!(fs::metadata(temp)?.len(), 0);
                    Err(io::Error::from_raw_os_error(5))
                },
                || panic!("must not reach commit after security failure"),
            )
            .unwrap_err();
            assert_eq!(error.raw_os_error(), Some(5));
            assert_eq!(fs::read(&path).unwrap(), b"old");
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            assert_eq!(acl_snapshot(&path), before);
            dir.assert_no_temps();
        }

        #[test]
        fn panic_restores_readonly_and_cleans_temp() {
            let dir = TestDir::new();
            let path = dir.0.join("old.dat");
            assert_eq!(write(&path, b"old", true), 0);
            assert!(
                catch_unwind(|| windows::atomic_write(&path, b"new", true, || panic!("test hook")))
                    .is_err()
            );
            assert_eq!(fs::read(&path).unwrap(), b"old");
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            dir.assert_no_temps();
        }

        #[test]
        fn blocked_commit_preserves_bytes_and_attributes() {
            let dir = TestDir::new();
            let path = dir.0.join("locked.dat");
            assert_eq!(write(&path, b"old", true), 0);
            // Allow reads/writes (including attribute changes), but deny delete/rename.
            let held = fs::OpenOptions::new()
                .read(true)
                .share_mode(1 | 2)
                .open(&path)
                .unwrap();
            // Windows/filesystem versions may report access denied or sharing violation.
            assert!(matches!(write(&path, b"replacement", true), 5 | 32));
            assert_eq!(fs::read(&path).unwrap(), b"old");
            assert!(fs::metadata(&path).unwrap().permissions().readonly());
            dir.assert_no_temps();
            drop(held);
        }

        #[test]
        fn path_errors_and_directory_rejected() {
            let dir = TestDir::new();
            assert_eq!(write(Path::new("relative.dat"), b"data", false), 87);
            assert_eq!(write(Path::new("C:relative.dat"), b"data", false), 87);
            assert_eq!(write(&dir.0, b"data", false), 5);
            assert_eq!(
                write(&dir.0.join("missing").join("data"), b"data", false),
                3
            );
            dir.assert_no_temps();
        }

        #[test]
        fn destination_symlink_rejected_when_creation_permitted() {
            let dir = TestDir::new();
            let target = dir.0.join("target");
            let link = dir.0.join("link");
            fs::write(&target, b"old").unwrap();
            match std::os::windows::fs::symlink_file(&target, &link) {
                Ok(()) => {
                    assert_eq!(write(&link, b"new", false), 5);
                    assert_eq!(fs::read(&target).unwrap(), b"old");
                    fs::remove_file(link).unwrap();
                }
                Err(e) if e.raw_os_error() == Some(1314) => {
                    eprintln!("symlink test skipped: Windows symlink privilege unavailable");
                }
                Err(e) => panic!("symlink creation failed: {e}"),
            }
            dir.assert_no_temps();
        }
    }
}

fn valid_layout_len(len: usize) -> bool {
    len >= 80 && (len - 64).is_multiple_of(16)
}

/// Check only the legacy salt(16), IV(16), ciphertext(>=16, multiple of 16),
/// tag(32) layout. Returns 0 for valid layout, 1 otherwise (including panic).
///
/// # Safety
/// For nonzero `len`, `data` must point to a readable allocation of at least
/// `len` bytes for the duration of this call. Null and excessive lengths are
/// rejected, but arbitrary dangling pointers cannot be detected by this ABI.
#[no_mangle]
pub unsafe extern "C" fn erica_validate_encrypted(data: *const u8, len: usize) -> i32 {
    catch_unwind(|| {
        if data.is_null() || len > isize::MAX as usize || !valid_layout_len(len) {
            1
        } else {
            // Layout is defined entirely by length; do not inspect secret bytes.
            0
        }
    })
    .unwrap_or(1)
}

/// Atomically write bytes to an absolute Windows path. Returns zero on success
/// or a Win32 error code. `read_only` must be 0 or 1. Null data is accepted only
/// when `data_len` is zero. No encrypted-layout validation is implicit.
///
/// # Safety
/// `path` must be aligned and readable for `path_len` UTF-16 code units, with no
/// terminator included. Nonempty `data` must be readable for `data_len` bytes.
/// Both allocations must remain valid and unmodified until this call returns.
/// The caller must ensure a trusted, stable parent directory and serialize
/// operations on the destination. Invalid non-null pointers cause undefined
/// behavior, not a recoverable error. See README.md for filesystem limitations.
#[no_mangle]
pub unsafe extern "C" fn erica_atomic_write(
    path: *const u16,
    path_len: usize,
    data: *const u8,
    data_len: usize,
    read_only: i32,
) -> u32 {
    catch_unwind(AssertUnwindSafe(|| {
        if path.is_null()
            || path_len == 0
            || path_len > isize::MAX as usize / 2
            || !(path as usize).is_multiple_of(std::mem::align_of::<u16>())
            || data_len > isize::MAX as usize
            || (data.is_null() && data_len != 0)
            || !matches!(read_only, 0 | 1)
        {
            return ERROR_INVALID_PARAMETER;
        }
        // SAFETY: caller guarantees readable buffers; sizes/alignment checked above.
        let path = unsafe { std::slice::from_raw_parts(path, path_len) };
        if path.contains(&0) {
            return ERROR_INVALID_PARAMETER;
        }
        let data = if data_len == 0 {
            &[]
        } else {
            // SAFETY: caller guarantees readable data; null and size checked above.
            unsafe { std::slice::from_raw_parts(data, data_len) }
        };
        platform_write(path, data, read_only != 0)
    }))
    .unwrap_or(ERROR_INTERNAL_ERROR)
}

#[cfg(not(windows))]
fn platform_write(_: &[u16], _: &[u8], _: bool) -> u32 {
    ERROR_NOT_SUPPORTED
}

#[cfg(windows)]
fn platform_write(path: &[u16], data: &[u8], read_only: bool) -> u32 {
    use std::os::windows::ffi::OsStringExt;
    let path = std::path::PathBuf::from(std::ffi::OsString::from_wide(path));
    if !path.is_absolute() || path.file_name().is_none() {
        return ERROR_INVALID_PARAMETER;
    }
    windows::atomic_write(&path, data, read_only, || Ok(()))
        .map_or_else(windows::error_code, |()| 0)
}

#[cfg(windows)]
mod windows {
    use std::ffi::c_void;
    use std::fs::{self, File, OpenOptions};
    use std::io::{self, Write};
    use std::os::windows::{
        ffi::OsStrExt,
        fs::{MetadataExt, OpenOptionsExt},
        io::AsRawHandle,
    };
    use std::path::{Path, PathBuf};

    const READONLY: u32 = 1;
    const DIRECTORY: u32 = 0x10;
    const NORMAL: u32 = 0x80;
    const REPARSE: u32 = 0x400;

    #[link(name = "advapi32")]
    unsafe extern "system" {
        fn SetFileInformationByHandle(
            handle: *mut c_void,
            class: i32,
            info: *const c_void,
            size: u32,
        ) -> i32;
        fn GetFileSecurityW(
            path: *const u16,
            information: u32,
            descriptor: *mut c_void,
            length: u32,
            needed: *mut u32,
        ) -> i32;
        fn SetFileSecurityW(path: *const u16, information: u32, descriptor: *const c_void) -> i32;
        fn GetSecurityDescriptorControl(
            descriptor: *const c_void,
            control: *mut u16,
            revision: *mut u32,
        ) -> i32;
    }

    pub(super) fn copy_dacl(source: &Path, destination: &Path) -> io::Result<()> {
        const DACL_INFORMATION: u32 = 4;
        const DACL_PROTECTED: u16 = 0x1000;
        let source = wide(source);
        let mut needed = 0u32;
        // SAFETY: source is terminated; null/zero requests the required buffer size.
        let result = unsafe {
            GetFileSecurityW(
                source.as_ptr(),
                DACL_INFORMATION,
                std::ptr::null_mut(),
                0,
                &mut needed,
            )
        };
        if result != 0 || io::Error::last_os_error().raw_os_error() != Some(122) || needed == 0 {
            return Err(io::Error::last_os_error());
        }
        // SECURITY_DESCRIPTOR requires DWORD alignment, unlike Vec<u8>.
        let mut descriptor = vec![0u32; (needed as usize).div_ceil(4)];
        // SAFETY: DWORD-aligned buffer has at least `needed` writable bytes.
        if unsafe {
            GetFileSecurityW(
                source.as_ptr(),
                DACL_INFORMATION,
                descriptor.as_mut_ptr().cast(),
                needed,
                &mut needed,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let mut control = 0u16;
        let mut revision = 0u32;
        // SAFETY: descriptor was initialized by GetFileSecurityW; outputs are writable.
        if unsafe {
            GetSecurityDescriptorControl(descriptor.as_ptr().cast(), &mut control, &mut revision)
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let protection = if control & DACL_PROTECTED != 0 {
            0x8000_0000
        } else {
            0x2000_0000
        };
        let destination = wide(destination);
        // SAFETY: destination is terminated, descriptor remains live and valid.
        if unsafe {
            SetFileSecurityW(
                destination.as_ptr(),
                DACL_INFORMATION | protection,
                descriptor.as_ptr().cast(),
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn MoveFileExW(existing: *const u16, new: *const u16, flags: u32) -> i32;
        fn SetFileAttributesW(path: *const u16, attributes: u32) -> i32;
    }
    #[link(name = "bcrypt")]
    unsafe extern "system" {
        fn BCryptGenRandom(algorithm: *mut c_void, buffer: *mut u8, len: u32, flags: u32) -> i32;
    }

    pub(super) fn error_code(error: io::Error) -> u32 {
        error
            .raw_os_error()
            .map_or(super::ERROR_INTERNAL_ERROR, |e| e as u32)
    }

    fn wide(path: &Path) -> Vec<u16> {
        path.as_os_str().encode_wide().chain(Some(0)).collect()
    }

    fn set_attributes(path: &Path, attributes: u32) -> io::Result<()> {
        let path = wide(path);
        // SAFETY: path is a live NUL-terminated UTF-16 buffer.
        if unsafe { SetFileAttributesW(path.as_ptr(), attributes) } == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    fn destination_attributes(path: &Path) -> io::Result<Option<u32>> {
        match fs::symlink_metadata(path) {
            Ok(metadata) => {
                let attrs = metadata.file_attributes();
                if attrs & (DIRECTORY | REPARSE) != 0 {
                    return Err(io::Error::from_raw_os_error(5));
                }
                Ok(Some(attrs))
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(e),
        }
    }

    struct TempFile(PathBuf, bool, File);
    impl Drop for TempFile {
        fn drop(&mut self) {
            if self.1 {
                return;
            }
            #[repr(C)]
            struct BasicInfo {
                creation: i64,
                access: i64,
                write: i64,
                change: i64,
                attributes: u32,
            }
            let basic = BasicInfo {
                creation: 0,
                access: 0,
                write: 0,
                change: 0,
                attributes: NORMAL,
            };
            let delete = 1i32;
            // SAFETY: cleanup handle obtained DELETE and FILE_WRITE_ATTRIBUTES before
            // applying the restrictive DACL; structures match Win32 layouts. Existing
            // handle rights survive DACL changes. No ACL widening is needed to clean up.
            unsafe {
                SetFileInformationByHandle(
                    self.2.as_raw_handle(),
                    0,
                    (&basic as *const BasicInfo).cast(),
                    std::mem::size_of::<BasicInfo>() as u32,
                );
                if SetFileInformationByHandle(
                    self.2.as_raw_handle(),
                    4,
                    (&delete as *const i32).cast(),
                    4,
                ) != 0
                {
                    return;
                }
            }
            // A read-only temporary must be made writable before deletion.
            if let Ok(meta) = fs::symlink_metadata(&self.0) {
                let attrs = meta.file_attributes();
                if attrs & READONLY != 0 {
                    let attrs = attrs & !READONLY;
                    let _ = set_attributes(&self.0, if attrs == 0 { NORMAL } else { attrs });
                }
                let _ = fs::remove_file(&self.0);
            }
        }
    }

    fn create_temp(parent: &Path) -> io::Result<(TempFile, File)> {
        for _ in 0..32 {
            let mut random = [0u8; 16];
            // SAFETY: OS RNG receives a writable buffer of exactly the supplied size.
            let status =
                unsafe { BCryptGenRandom(std::ptr::null_mut(), random.as_mut_ptr(), 16, 2) };
            if status < 0 {
                // NTSTATUS is not a Win32 error code; never return it as one.
                return Err(io::Error::from_raw_os_error(31));
            }
            let suffix: String = random.iter().map(|b| format!("{b:02x}")).collect();
            let path = parent.join(format!(".erica-{suffix}.tmp"));
            match OpenOptions::new()
                .write(true)
                .access_mode(0x4000_0000 | 0x0001_0000)
                .create_new(true)
                .open(&path)
            {
                Ok(file) => {
                    let cleanup = match file.try_clone() {
                        Ok(handle) => handle,
                        Err(error) => {
                            drop(file);
                            let _ = fs::remove_file(&path);
                            return Err(error);
                        }
                    };
                    return Ok((TempFile(path, false, cleanup), file));
                }
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e),
            }
        }
        Err(io::Error::from_raw_os_error(80))
    }

    struct RestoreAttributes<'a> {
        path: &'a Path,
        attributes: Option<u32>,
    }
    impl RestoreAttributes<'_> {
        fn restore(&mut self) -> io::Result<()> {
            if let Some(attributes) = self.attributes {
                set_attributes(self.path, attributes)?;
                self.attributes = None;
            }
            Ok(())
        }
    }
    impl Drop for RestoreAttributes<'_> {
        fn drop(&mut self) {
            let _ = self.restore();
        }
    }

    // The hook is private, not exported, and only tests supply a failing closure.
    pub(super) fn atomic_write(
        path: &Path,
        data: &[u8],
        read_only: bool,
        before_commit: impl FnOnce() -> io::Result<()>,
    ) -> io::Result<()> {
        atomic_write_with_security(path, data, read_only, copy_dacl, before_commit)
    }

    pub(super) fn atomic_write_with_security(
        path: &Path,
        data: &[u8],
        read_only: bool,
        apply_security: impl FnOnce(&Path, &Path) -> io::Result<()>,
        before_commit: impl FnOnce() -> io::Result<()>,
    ) -> io::Result<()> {
        let exists = destination_attributes(path)?.is_some();
        let parent = path
            .parent()
            .ok_or_else(|| io::Error::from_raw_os_error(87))?;
        let (mut temp, mut file) = create_temp(parent)?;
        if exists {
            // Apply the old access policy while the temporary is still empty.
            // Any failure aborts before writing data or modifying the destination.
            apply_security(path, &temp.0)?;
        }
        file.write_all(data)?;
        file.sync_all()?;
        drop(file);
        if read_only {
            let attrs = fs::symlink_metadata(&temp.0)?.file_attributes();
            set_attributes(&temp.0, (attrs & !NORMAL) | READONLY)?;
        }
        let attrs = destination_attributes(path)?;
        let mut restore = RestoreAttributes {
            path,
            attributes: None,
        };
        if let Some(attrs) = attrs.filter(|attrs| attrs & READONLY != 0) {
            let writable = attrs & !READONLY;
            set_attributes(path, if writable == 0 { NORMAL } else { writable })?;
            restore.attributes = Some(attrs);
        }
        let result = before_commit().and_then(|()| {
            let from = wide(&temp.0);
            let to = wide(path);
            // SAFETY: both paths are live NUL-terminated UTF-16 buffers.
            if unsafe { MoveFileExW(from.as_ptr(), to.as_ptr(), 0x1 | 0x8) } == 0 {
                Err(io::Error::last_os_error())
            } else {
                Ok(())
            }
        });
        match result {
            Ok(()) => {
                restore.attributes = None;
                // The move consumed the temp path; do not touch it during cleanup.
                temp.1 = true;
                Ok(())
            }
            Err(error) => {
                // A restoration failure is more actionable than the commit error.
                restore.restore()?;
                Err(error)
            }
        }
    }
}
