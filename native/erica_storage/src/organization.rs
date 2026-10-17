//! Organization ABI 2. Crypto, validation, DPAPI and guarded organization I/O.
use aes_gcm::{aead::AeadInPlace, Aes256Gcm, KeyInit, Nonce, Tag};
use base64::{engine::general_purpose::STANDARD, Engine};
use sha2::{Digest, Sha256};
use std::{fs, io::Read, panic::catch_unwind, path::Path, ptr};
use subtle::ConstantTimeEq;
use zeroize::{Zeroize, Zeroizing};

const INVALID: u32 = 1;
const ENVELOPE: u32 = 2;
const INTEGRITY: u32 = 3;
const DPAPI: u32 = 4;
const SYSTEM: u32 = 5;
const DESTINATION: u32 = 6;
const IO: u32 = 7;
const PANIC: u32 = 1359;
const MAGIC: &[u8; 8] = b"ERICAORG";
const CHECK_DOMAIN: &[u8] = b"ERICAORG\0CHECK\x01";
const KEY_DOMAIN: &[u8] = b"ERICAORG\0TOKENS\x01";
const DPAPI_PAYLOAD: &[u8] = b"ERICAORG-TOKENS\x01";
type Result<T> = std::result::Result<T, u32>;
type Secret = Zeroizing<Vec<u8>>;

fn equal(a: &[u8], b: &[u8]) -> bool {
    bool::from(a.ct_eq(b))
}

fn token(value: &[u8]) -> Result<()> {
    if value.len() == 16 && value.iter().all(u8::is_ascii_digit) {
        Ok(())
    } else {
        Err(INVALID)
    }
}

fn pair(value: &[u8]) -> Result<()> {
    if value.len() != 32 {
        return Err(INVALID);
    }
    token(&value[..16])?;
    token(&value[16..])?;
    if equal(&value[..16], &value[16..]) {
        Err(INVALID)
    } else {
        Ok(())
    }
}

fn check(value: &[u8]) -> Result<Vec<u8>> {
    token(value)?;
    let mut digest = Sha256::new();
    digest.update(CHECK_DOMAIN);
    digest.update(value);
    let mut hash = digest.finalize();
    // Public ~17-bit typo check, not authentication. Preserve leading zeroes.
    let number = u64::from_be_bytes(hash[..8].try_into().map_err(|_| SYSTEM)?) % 100_000;
    let result = format!("{number:05}").into_bytes();
    hash.as_mut_slice().zeroize();
    Ok(result)
}

fn derive(value: &[u8], salt: &[u8]) -> Result<Zeroizing<[u8; 32]>> {
    let mut password = Zeroizing::new(Vec::with_capacity(KEY_DOMAIN.len() + 32));
    password.extend_from_slice(KEY_DOMAIN);
    password.extend_from_slice(value);
    let mut key = Zeroizing::new([0u8; 32]);
    let params = scrypt::Params::new(15, 8, 1, 32).map_err(|_| SYSTEM)?;
    scrypt::scrypt(&password, salt, &params, key.as_mut()).map_err(|_| SYSTEM)?;
    Ok(key)
}

fn encrypt_fixed(value: &[u8], raw: &[u8], salt: &[u8; 16], nonce: &[u8; 12]) -> Result<Secret> {
    pair(value)?;
    let size = raw
        .len()
        .checked_add(53)
        .filter(|n| *n <= isize::MAX as usize)
        .ok_or(INVALID)?;
    let mut out = Zeroizing::new(Vec::with_capacity(size));
    out.extend_from_slice(MAGIC);
    out.push(1);
    out.extend_from_slice(salt);
    out.extend_from_slice(nonce);
    let key = derive(value, salt)?;
    let cipher = Aes256Gcm::new_from_slice(key.as_ref()).map_err(|_| SYSTEM)?;
    let mut body = Zeroizing::new(raw.to_vec());
    let tag = cipher
        .encrypt_in_place_detached(Nonce::from_slice(nonce), &out, &mut body)
        .map_err(|_| SYSTEM)?;
    out.extend_from_slice(&body);
    out.extend_from_slice(&tag);
    Ok(out)
}

fn encrypt(value: &[u8], raw: &[u8]) -> Result<Secret> {
    let mut random = Zeroizing::new([0u8; 28]);
    random_fill(random.as_mut())?;
    encrypt_fixed(
        value,
        raw,
        random[..16].try_into().map_err(|_| SYSTEM)?,
        random[16..].try_into().map_err(|_| SYSTEM)?,
    )
}

fn decrypt(value: &[u8], data: &[u8]) -> Result<Secret> {
    pair(value)?;
    if data.len() < 53 || !data.starts_with(MAGIC) || data[8] != 1 {
        return Err(ENVELOPE);
    }
    let key = derive(value, &data[9..25])?;
    let cipher = Aes256Gcm::new_from_slice(key.as_ref()).map_err(|_| SYSTEM)?;
    let end = data.len() - 16;
    let mut raw = Zeroizing::new(data[37..end].to_vec());
    cipher
        .decrypt_in_place_detached(
            Nonce::from_slice(&data[25..37]),
            &data[..37],
            &mut raw,
            Tag::from_slice(&data[end..]),
        )
        .map_err(|_| INTEGRITY)?;
    Ok(raw)
}

fn generate_with(mut fill: impl FnMut(&mut [u8]) -> Result<()>) -> Result<Secret> {
    let mut out = Zeroizing::new(Vec::with_capacity(32));
    let mut bytes = Zeroizing::new([0u8; 64]);
    loop {
        fill(bytes.as_mut())?;
        for &byte in bytes.iter() {
            // 250 is divisible by ten: rejection removes modulo bias.
            if byte < 250 {
                out.push(b'0' + byte % 10);
            }
            if out.len() == 32 {
                if !equal(&out[..16], &out[16..]) {
                    return Ok(out);
                }
                out[16..].zeroize();
                out.truncate(16);
            }
        }
    }
}

#[cfg(windows)]
fn random_fill(out: &mut [u8]) -> Result<()> {
    #[link(name = "bcrypt")]
    extern "system" {
        fn BCryptGenRandom(
            algorithm: *mut std::ffi::c_void,
            buffer: *mut u8,
            len: u32,
            flags: u32,
        ) -> i32;
    }
    for chunk in out.chunks_mut(u32::MAX as usize) {
        // SAFETY: BCRYPT_USE_SYSTEM_PREFERRED_RNG takes null algorithm; chunk is writable.
        if unsafe { BCryptGenRandom(ptr::null_mut(), chunk.as_mut_ptr(), chunk.len() as u32, 2) }
            < 0
        {
            return Err(SYSTEM);
        }
    }
    Ok(())
}

#[cfg(not(windows))]
fn random_fill(_: &mut [u8]) -> Result<()> {
    Err(SYSTEM)
}

#[cfg(windows)]
fn dpapi(data: &[u8], protect: bool) -> Result<Secret> {
    use std::ffi::c_void;
    #[repr(C)]
    struct Blob {
        len: u32,
        data: *mut u8,
    }
    #[repr(C)]
    struct Prompt {
        size: u32,
        flags: u32,
        hwnd: *mut c_void,
        text: *const u16,
    }
    #[link(name = "crypt32")]
    extern "system" {
        fn CryptProtectData(
            input: *const Blob,
            description: *const u16,
            entropy: *const Blob,
            reserved: *mut c_void,
            prompt: *const Prompt,
            flags: u32,
            output: *mut Blob,
        ) -> i32;
        fn CryptUnprotectData(
            input: *const Blob,
            description: *mut *mut u16,
            entropy: *const Blob,
            reserved: *mut c_void,
            prompt: *const Prompt,
            flags: u32,
            output: *mut Blob,
        ) -> i32;
    }
    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
    }
    struct Output(Blob);
    impl Drop for Output {
        fn drop(&mut self) {
            if !self.0.data.is_null() {
                // SAFETY: DPAPI owns this LocalAlloc buffer until LocalFree; wipe first.
                unsafe {
                    std::slice::from_raw_parts_mut(self.0.data, self.0.len as usize).zeroize();
                    LocalFree(self.0.data.cast());
                }
            }
        }
    }
    let mut source = Zeroizing::new(data.to_vec());
    let input = Blob {
        len: u32::try_from(data.len()).map_err(|_| INVALID)?,
        data: source.as_mut_ptr(),
    };
    let mut output = Output(Blob {
        len: 0,
        data: ptr::null_mut(),
    });
    // SAFETY: all structures/buffers are live; optional UI/entropy/description are null.
    // CRYPTPROTECT_UI_FORBIDDEN only: current user, never LOCAL_MACHINE or fallback.
    let ok = unsafe {
        if protect {
            CryptProtectData(
                &input,
                ptr::null(),
                ptr::null(),
                ptr::null_mut(),
                ptr::null(),
                1,
                &mut output.0,
            )
        } else {
            CryptUnprotectData(
                &input,
                ptr::null_mut(),
                ptr::null(),
                ptr::null_mut(),
                ptr::null(),
                1,
                &mut output.0,
            )
        }
    };
    if ok == 0
        || output.0.data.is_null()
        || output.0.len == 0
        || output.0.len as usize > isize::MAX as usize
    {
        return Err(DPAPI);
    }
    // SAFETY: successful DPAPI returned a buffer of the indicated size; Output owns it.
    Ok(Zeroizing::new(
        unsafe { std::slice::from_raw_parts(output.0.data, output.0.len as usize) }.to_vec(),
    ))
}

#[cfg(not(windows))]
fn dpapi(_: &[u8], _: bool) -> Result<Secret> {
    Err(DPAPI)
}

fn path(data: &[u8]) -> Result<&Path> {
    let text = std::str::from_utf8(data).map_err(|_| INVALID)?;
    let path = Path::new(text);
    if text.is_empty() || text.contains('\0') || !path.is_absolute() || path.file_name().is_none() {
        return Err(INVALID);
    }
    Ok(path)
}

fn classify_path(path: &Path) -> Result<bool> {
    let mut file = fs::File::open(path).map_err(|_| IO)?;
    let mut header = [0; 8];
    let mut count = 0;
    while count < 8 {
        match file.read(&mut header[count..]) {
            Ok(0) => break,
            Ok(n) => count += n,
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(_) => return Err(IO),
        }
    }
    Ok(count == 8 && &header == MAGIC)
}

fn verify(path: &Path, tokens: Option<&[u8]>) -> Result<()> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(_) => return Err(IO),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(IO);
    }
    if metadata.len() == 0 {
        return Ok(());
    }
    if classify_path(path)? != tokens.is_some() {
        return Err(DESTINATION);
    }
    if let Some(tokens) = tokens {
        let data = Zeroizing::new(fs::read(path).map_err(|_| IO)?);
        drop(decrypt(tokens, &data)?);
    }
    Ok(())
}

#[cfg(windows)]
fn write_document(tokens: &[u8], path: &Path, raw: &[u8]) -> Result<()> {
    verify(path, Some(tokens))?;
    let encrypted = encrypt(tokens, raw)?;
    let failed = std::cell::Cell::new(IO);
    // Existing native writer preserves DACL, restores attributes on failure, and
    // replaces atomically. Recheck after preparing temp, immediately before commit.
    super::windows::atomic_write(path, &encrypted, true, || {
        verify(path, Some(tokens)).map_err(|status| {
            failed.set(status);
            std::io::Error::other("organization destination verification failed")
        })
    })
    .map_err(|_| failed.get())
}

#[cfg(not(windows))]
fn write_document(_: &[u8], _: &Path, _: &[u8]) -> Result<()> {
    Err(SYSTEM)
}

fn dispatch(op: u32, input: &[u8]) -> Result<Secret> {
    let output = match op {
        1 => {
            pair(input)?;
            input.to_vec()
        }
        2 => check(input)?,
        3 => {
            if input.len() != 42 || !input[32..].iter().all(u8::is_ascii_digit) {
                return Err(INVALID);
            }
            pair(&input[..32])?;
            let a = check(&input[..16])?;
            let b = check(&input[16..32])?;
            let ok = equal(&a, &input[32..37]) & equal(&b, &input[37..]);
            if !ok {
                return Err(INVALID);
            }
            input[..32].to_vec()
        }
        4 => {
            if !input.is_empty() {
                return Err(INVALID);
            }
            return generate_with(random_fill);
        }
        5 => vec![u8::from(input.starts_with(MAGIC))],
        6 | 7 => {
            if input.len() < 32 {
                return Err(INVALID);
            }
            pair(&input[..32])?;
            return if op == 6 {
                encrypt(&input[..32], &input[32..])
            } else {
                decrypt(&input[..32], &input[32..])
            };
        }
        8 => {
            pair(input)?;
            let mut payload = Zeroizing::new(DPAPI_PAYLOAD.to_vec());
            payload.extend_from_slice(input);
            STANDARD.encode(dpapi(&payload, true)?).into_bytes()
        }
        9 => {
            let blob = Zeroizing::new(STANDARD.decode(input).map_err(|_| INVALID)?);
            if blob.is_empty() || STANDARD.encode(&blob).as_bytes() != input {
                return Err(INVALID);
            }
            let payload = dpapi(&blob, false)?;
            if payload.len() != DPAPI_PAYLOAD.len() + 32 || !payload.starts_with(DPAPI_PAYLOAD) {
                return Err(INVALID);
            }
            let restored = &payload[DPAPI_PAYLOAD.len()..];
            pair(restored)?;
            restored.to_vec()
        }
        10 => {
            let (tokens, rest) = match input.first() {
                Some(0) => (None, &input[1..]),
                Some(1) if input.len() >= 33 => {
                    pair(&input[1..33])?;
                    (Some(&input[1..33]), &input[33..])
                }
                _ => return Err(INVALID),
            };
            verify(path(rest)?, tokens)?;
            Vec::new()
        }
        11 => vec![u8::from(classify_path(path(input)?)?)],
        12 => {
            if input.len() < 36 {
                return Err(INVALID);
            }
            pair(&input[..32])?;
            let len = u32::from_le_bytes(input[32..36].try_into().map_err(|_| INVALID)?) as usize;
            let end = 36usize
                .checked_add(len)
                .filter(|n| *n <= input.len())
                .ok_or(INVALID)?;
            write_document(&input[..32], path(&input[36..end])?, &input[end..])?;
            Vec::new()
        }
        13 => {
            if input.len() < 32 {
                return Err(INVALID);
            }
            pair(&input[..32])?;
            let data = Zeroizing::new(fs::read(path(&input[32..])?).map_err(|_| IO)?);
            return decrypt(&input[..32], &data);
        }
        _ => return Err(INVALID),
    };
    Ok(Zeroizing::new(output))
}

#[no_mangle]
pub extern "C" fn erica_organization_abi_version() -> u32 {
    catch_unwind(|| 2).unwrap_or(2)
}

fn region(pointer: usize, len: usize) -> Option<std::ops::Range<usize>> {
    pointer.checked_add(len).map(|end| pointer..end)
}
fn overlaps(a: &std::ops::Range<usize>, b: &std::ops::Range<usize>) -> bool {
    a.start < b.end && b.start < a.end
}

/// Execute organization ABI 2 operation. Zero status means success.
///
/// # Safety
/// Input must be readable for len bytes, live and immutable during the call.
/// Outputs must be distinct aligned writable pointer/usize slots, and must not
/// overlap input. Arbitrary invalid pointers cannot be detected. On valid output
/// slots every failure sets null/zero. Successful nonempty output must be freed
/// exactly once by erica_org_free, with its original pointer and length.
#[no_mangle]
pub unsafe extern "C" fn erica_org_call(
    op: u32,
    input: *const u8,
    len: usize,
    out: *mut *mut u8,
    out_len: *mut usize,
) -> u32 {
    catch_unwind(|| {
        let valid_out =
            !out.is_null() && (out as usize).is_multiple_of(std::mem::align_of::<*mut u8>());
        let valid_len =
            !out_len.is_null() && (out_len as usize).is_multiple_of(std::mem::align_of::<usize>());
        // SAFETY: caller promises writable slots; each is checked for null/alignment.
        unsafe {
            if valid_out {
                out.write(ptr::null_mut());
            }
            if valid_len {
                out_len.write(0);
            }
        }
        if !valid_out || !valid_len || len > isize::MAX as usize || (input.is_null() && len != 0) {
            return INVALID;
        }
        let Some(a) = region(out as usize, std::mem::size_of::<*mut u8>()) else {
            return INVALID;
        };
        let Some(b) = region(out_len as usize, std::mem::size_of::<usize>()) else {
            return INVALID;
        };
        let Some(c) = region(input as usize, len) else {
            return INVALID;
        };
        if overlaps(&a, &b) || overlaps(&a, &c) || overlaps(&b, &c) {
            return INVALID;
        }
        let input = if len == 0 {
            &[]
        } else {
            // SAFETY: caller guarantees readable bytes; size/null checked above.
            unsafe { std::slice::from_raw_parts(input, len) }
        };
        match dispatch(op, input) {
            Ok(mut value) => {
                if value.len() > isize::MAX as usize {
                    return SYSTEM;
                }
                if !value.is_empty() {
                    let buffer = std::mem::take(&mut *value).into_boxed_slice();
                    let len = buffer.len();
                    let pointer = Box::into_raw(buffer).cast::<u8>();
                    // SAFETY: valid disjoint writable slots checked above.
                    unsafe {
                        out.write(pointer);
                        out_len.write(len);
                    }
                }
                0
            }
            Err(status) => status,
        }
    })
    .unwrap_or(PANIC)
}

/// Wipe and release an output from erica_org_call; null/zero is a no-op.
///
/// # Safety
/// Nonempty pointer/len must be the exact live allocation returned by this DLL,
/// not previously freed or mutated concurrently. No foreign allocations allowed.
#[no_mangle]
pub unsafe extern "C" fn erica_org_free(out: *mut u8, len: usize) {
    let _ = catch_unwind(|| {
        if out.is_null()
            || len == 0
            || len > isize::MAX as usize
            || region(out as usize, len).is_none()
        {
            return;
        }
        // SAFETY: caller guarantees exact ownership/length of our boxed slice.
        let mut buffer = unsafe { Box::from_raw(ptr::slice_from_raw_parts_mut(out, len)) };
        buffer.zeroize();
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    const PAIR: &[u8; 32] = b"01234567890123459876543210987654";

    fn unhex(value: &str) -> Vec<u8> {
        value
            .as_bytes()
            .as_chunks::<2>()
            .0
            .iter()
            .map(|c| {
                let text = std::str::from_utf8(c).unwrap();
                u8::from_str_radix(text, 16).unwrap()
            })
            .collect()
    }

    fn call(op: u32, input: &[u8]) -> (u32, Secret) {
        let mut output = ptr::null_mut();
        let mut len = 0;
        // SAFETY: readable input, valid distinct aligned outputs; exact returned
        // allocation is copied then released once by the paired export.
        unsafe {
            let status = erica_org_call(op, input.as_ptr(), input.len(), &mut output, &mut len);
            if status != 0 || len == 0 {
                assert!(output.is_null());
                assert_eq!(len, 0);
                return (status, Zeroizing::new(Vec::new()));
            }
            let result = Zeroizing::new(std::slice::from_raw_parts(output, len).to_vec());
            erica_org_free(output, len);
            (status, result)
        }
    }

    #[test]
    fn validation_checks_and_order() {
        assert_eq!(erica_organization_abi_version(), 2);
        assert_eq!(super::super::erica_storage_abi_version(), 1);
        assert_eq!(&*call(1, PAIR).1, PAIR);
        for bad in [
            b"".as_slice(),
            b"01234567890123450123456789012345",
            b"0123456789012345987654321098765x",
            b"01234567890123459876543210987654 ",
        ] {
            assert_eq!(call(1, bad).0, INVALID);
        }
        assert_eq!(&*call(2, &PAIR[..16]).1, b"03129");
        assert_eq!(&*call(2, &PAIR[16..]).1, b"77252");
        assert_eq!(&*call(2, b"0000000000000006").1, b"05553");
        assert_eq!(
            call(2, "１２３４５６７８９０１２３４５６".as_bytes()).0,
            INVALID
        );
        let mut input = PAIR.to_vec();
        input.extend_from_slice(b"0312977252");
        assert_eq!(input.len(), 42);
        assert_eq!(&*call(3, &input).1, PAIR);
        input[32] = b'f';
        assert_eq!(call(3, &input).0, INVALID);
        input[32] = b'1';
        assert_eq!(call(3, &input).0, INVALID);
        assert_eq!(call(4, b"extra").0, INVALID);
        for input in [
            b"ERICAORG".as_slice(),
            b"ERICAORG\xff",
            b"ERICAORG\x01short",
        ] {
            assert_eq!(&*call(5, input).1, &[1]);
        }
        assert_eq!(&*call(5, b"ERICAOR").1, &[0]);
    }

    #[test]
    fn checks_are_strict_five_ascii_digits() {
        for bad in [
            b"".as_slice(),
            b"3129", // leading zero must not be dropped
            b"003129",
            b"F8E64DFDC90B", // organization ABI 1 checks are not accepted
            b"03129 ",
            b" 3129",
            b"0312\n",
            b"0312\0",
            b"+3129",
            b"0312A",
            "０３１２９".as_bytes(),
            "٠٣١٢٩".as_bytes(),
        ] {
            for checks in [(bad, b"77252".as_slice()), (b"03129".as_slice(), bad)] {
                let mut input = PAIR.to_vec();
                input.extend_from_slice(checks.0);
                input.extend_from_slice(checks.1);
                assert_eq!(call(3, &input).0, INVALID, "checks {checks:?}");
            }
        }
        let mut old_wire = PAIR.to_vec();
        old_wire.extend_from_slice(b"F8E64DFDC90B26B993702A95");
        assert_eq!(call(3, &old_wire).0, INVALID);
        let mut swapped = PAIR.to_vec();
        swapped.extend_from_slice(b"7725203129");
        assert_eq!(call(3, &swapped).0, INVALID);
    }

    #[test]
    fn legacy_python_v1_fixture() {
        // Independently captured using pre-migration Python cryptography code.
        let data = unhex("45524943414f5247010393de9a44654d4adef5e652cf1be99f0c9b4dcf9c87379707777ccc860ff6eb80152b945c325248b0930e3a94a4ac6142112d719f17ed5e2a57d2445d443276e7b12815493a9a29d8a4502c4608ff");
        let raw = unhex("4578697374696e6720507974686f6e206f7267616e697a6174696f6e2066696c6500ff");
        assert_eq!(&*decrypt(PAIR, &data).unwrap(), &raw);
        let encrypted = encrypt_fixed(
            PAIR,
            &raw,
            data[9..25].try_into().unwrap(),
            data[25..37].try_into().unwrap(),
        )
        .unwrap();
        assert_eq!(&*encrypted, &data);
    }

    #[test]
    fn envelope_authentication_and_no_partial_output() {
        let encrypted = encrypt_fixed(PAIR, b"secret\0\xff", &[1; 16], &[2; 12]).unwrap();
        let mut input = PAIR.to_vec();
        input.extend_from_slice(&encrypted);
        assert_eq!(&*call(7, &input).1, b"secret\0\xff");
        // Wrong ordered pair, salt, nonce, ciphertext, and tag all authenticate.
        for index in [0, 32 + 9, 32 + 25, 32 + 37, input.len() - 1] {
            let mut changed = input.clone();
            changed[index] ^= 1;
            assert_eq!(call(7, &changed).0, INTEGRITY);
        }
        let mut swapped = PAIR[16..].to_vec();
        swapped.extend_from_slice(&PAIR[..16]);
        swapped.extend_from_slice(&encrypted);
        assert_eq!(call(7, &swapped).0, INTEGRITY);
        for index in [32, 40] {
            let mut changed = input.clone();
            changed[index] ^= 1;
            assert_eq!(call(7, &changed).0, ENVELOPE);
        }
        assert_eq!(call(7, &input[..64]).0, ENVELOPE);
        let empty = encrypt_fixed(PAIR, b"", &[3; 16], &[4; 12]).unwrap();
        assert_eq!(empty.len(), 53);
        assert!(decrypt(PAIR, &empty).unwrap().is_empty());
    }

    #[test]
    fn generation_rejects_bias_and_duplicate_pair() {
        let mut iteration = 0;
        let generated = generate_with(|bytes| {
            bytes.fill(255);
            if iteration == 0 {
                bytes[..16].fill(0);
                bytes[16..32].fill(250); // rejected, not converted to zero
                bytes[32..48].fill(0); // duplicate second token is discarded
                bytes[48..].fill(249); // accepted as digit9
            }
            iteration += 1;
            Ok(())
        })
        .unwrap();
        assert_eq!(&*generated, b"00000000000000009999999999999999");
        assert_eq!(iteration, 1);
        assert_eq!(generate_with(|_| Err(SYSTEM)).unwrap_err(), SYSTEM);
    }

    #[test]
    fn ffi_invalid_buffers_and_wire_inputs() {
        let mut output = ptr::dangling_mut::<u8>();
        let mut len = 123;
        // SAFETY: invalid counts/null/alignment are checked without dereference;
        // all other buffers/slots point to live allocations.
        unsafe {
            assert_eq!(
                erica_org_call(1, ptr::null(), 32, &mut output, &mut len),
                INVALID
            );
            assert!(output.is_null());
            assert_eq!(len, 0);
            assert_eq!(
                erica_org_call(1, PAIR.as_ptr(), usize::MAX, &mut output, &mut len),
                INVALID
            );
            assert_eq!(
                erica_org_call(1, PAIR.as_ptr(), 32, ptr::null_mut(), &mut len),
                INVALID
            );
            assert_eq!(len, 0);
            assert_eq!(
                erica_org_call(1, PAIR.as_ptr(), 32, &mut output, ptr::null_mut()),
                INVALID
            );
            assert!(output.is_null());
            let mut aligned = [0usize; 3];
            let misaligned = aligned.as_mut_ptr().cast::<u8>().add(1).cast::<usize>();
            assert_eq!(
                erica_org_call(1, PAIR.as_ptr(), 32, &mut output, misaligned),
                INVALID
            );
            assert_eq!(
                erica_org_call(
                    1,
                    PAIR.as_ptr(),
                    32,
                    aligned.as_mut_ptr().cast(),
                    aligned.as_mut_ptr()
                ),
                INVALID
            );
            assert_eq!(erica_org_call(5, ptr::null(), 0, &mut output, &mut len), 0);
            assert_eq!(len, 1);
            erica_org_free(output, len);
            erica_org_free(ptr::null_mut(), 0);
            erica_org_free(ptr::null_mut(), 25);
        }
        for (op, input) in [
            (0, b"".as_slice()),
            (6, b""),
            (7, b""),
            (8, b""),
            (9, b""),
            (9, b"===="),
            (9, b"YQ==\n"),
            (9, b"YR=="),
            (10, b""),
            (10, b"\x02C:\\x"),
            (11, b"relative"),
            (11, b"C:\\bad\0file"),
            (12, b""),
            (13, b""),
        ] {
            assert_eq!(call(op, input).0, INVALID, "op {op}");
        }
        let mut malformed_write = PAIR.to_vec();
        malformed_write.extend_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(call(12, &malformed_write).0, INVALID);
    }

    #[cfg(windows)]
    #[test]
    fn windows_random_and_dpapi() {
        let a = call(4, b"");
        let b = call(4, b"");
        assert_eq!(a.0, 0);
        assert_eq!(b.0, 0);
        assert_ne!(&*a.1, &*b.1);
        pair(&a.1).unwrap();
        pair(&b.1).unwrap();
        let first = call(6, PAIR);
        let second = call(6, PAIR);
        assert_eq!(first.0, 0);
        assert_eq!(second.0, 0);
        assert_ne!(&*first.1, &*second.1);
        let protected = call(8, PAIR);
        assert_eq!(protected.0, 0);
        assert!(!protected.1.windows(16).any(|w| w == &PAIR[..16]));
        assert_eq!(&*call(9, &protected.1).1, PAIR);
        let wrong_payload = dpapi(b"wrong payload", true).unwrap();
        assert_eq!(
            call(9, STANDARD.encode(&wrong_payload).as_bytes()).0,
            INVALID
        );
        let mut corrupt = STANDARD.decode(&protected.1).unwrap();
        let end = corrupt.len() - 1;
        corrupt[end] ^= 1;
        assert_eq!(call(9, STANDARD.encode(&corrupt).as_bytes()).0, DPAPI);
    }

    #[cfg(windows)]
    #[test]
    fn windows_guarded_atomic_document_io() {
        let mut random = [0u8; 8];
        random_fill(&mut random).unwrap();
        let dir = std::env::temp_dir().join(format!("erica-org-{:x}", u64::from_le_bytes(random)));
        fs::create_dir(&dir).unwrap();
        struct Cleanup(std::path::PathBuf);
        impl Drop for Cleanup {
            fn drop(&mut self) {
                for file in fs::read_dir(&self.0).unwrap().flatten() {
                    let mut permissions = file.metadata().unwrap().permissions();
                    #[allow(clippy::permissions_set_readonly_false)]
                    // Windows-only cleanup of native read-only results.
                    permissions.set_readonly(false);
                    let _ = fs::set_permissions(file.path(), permissions);
                }
                let _ = fs::remove_dir_all(&self.0);
            }
        }
        let _cleanup = Cleanup(dir.clone());
        let file = dir.join("組織-é-🔒.enc");
        let path = file.to_str().unwrap().as_bytes();
        let mut org_guard = vec![1];
        org_guard.extend_from_slice(PAIR);
        org_guard.extend_from_slice(path);
        let mut password_guard = vec![0];
        password_guard.extend_from_slice(path);
        assert_eq!(call(10, &org_guard).0, 0);
        assert_eq!(call(10, &password_guard).0, 0);
        assert_eq!(call(11, path).0, IO);
        let mut write = PAIR.to_vec();
        write.extend_from_slice(&(path.len() as u32).to_le_bytes());
        write.extend_from_slice(path);
        write.extend_from_slice(b"first\0\xff");
        assert_eq!(call(12, &write).0, 0);
        assert!(fs::metadata(&file).unwrap().permissions().readonly());
        assert_eq!(&*call(11, path).1, &[1]);
        let mut read = PAIR.to_vec();
        read.extend_from_slice(path);
        assert_eq!(&*call(13, &read).1, b"first\0\xff");
        assert_eq!(call(10, &password_guard).0, DESTINATION);
        assert_eq!(call(10, &org_guard).0, 0);
        let preserved = fs::read(&file).unwrap();
        write[0] = b'2';
        assert_eq!(call(12, &write).0, INTEGRITY);
        assert_eq!(fs::read(&file).unwrap(), preserved);
        write[0] = PAIR[0];
        assert_eq!(call(12, &write).0, 0); // read-only replacement
        let other = dir.join("password.enc");
        fs::write(&other, b"legacy password data").unwrap();
        assert_eq!(verify(&other, None), Ok(()));
        assert_eq!(verify(&other, Some(PAIR)), Err(DESTINATION));
        assert_eq!(write_document(PAIR, &other, b"overwrite"), Err(DESTINATION));
        assert_eq!(fs::read(&other).unwrap(), b"legacy password data");
        let empty = dir.join("empty.enc");
        fs::write(&empty, b"").unwrap();
        assert_eq!(verify(&empty, None), Ok(()));
        assert_eq!(verify(&empty, Some(PAIR)), Ok(()));
        let unsupported = dir.join("future.enc");
        fs::write(&unsupported, b"ERICAORG\xff").unwrap();
        assert_eq!(verify(&unsupported, None), Err(DESTINATION));
        assert_eq!(verify(&unsupported, Some(PAIR)), Err(ENVELOPE));
        assert!(!fs::read_dir(&dir)
            .unwrap()
            .flatten()
            .any(|e| e.file_name().to_string_lossy().starts_with(".erica-")));
    }
}
