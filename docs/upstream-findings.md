# Prepared upstream findings

All entries are local preparation only. No issue, pull request, comment, or maintainer contact has occurred.

## 1. midenup Windows PATH construction

- **Source:** `0xMiden/midenup`, commit `734b14aaa2e92d7b816a92bc0aa2cc97f954b27b`
- **Status:** `LOCAL_PATCH_READY`, `NOT_SUBMITTED`
- **Finding:** Hard-coded colon joining produces an invalid Windows PATH and converts path data through strings.
- **Fix:** Use `std::env::split_paths` and `join_paths`, preserve `OsString`, and retain Cargo-bin and active-toolchain ordering.
- **Validation:** Windows GNU `cargo check --lib` passed; diff and formatting checks passed. Focused GNU tests are blocked by pre-existing Unix-only test modules. MSVC is unverified.

## 2. Web SDK wallet lockfile drift

- **Source:** `0xMiden/web-sdk`, commit `029aba8c92562786e16c22fac9247c3c8d64f091`
- **Status:** `LOCAL_FIX_VALIDATED`, `NOT_SUBMITTED`
- **Finding:** The wallet example manifest declares `@miden-sdk/*` 0.17.3 while its direct pnpm importer resolves 0.14.5.
- **Fix:** Regenerate the isolated example lockfile with the pinned pnpm version.
- **Validation:** `MIDEN016-SDK-002` is present before and absent after the local correction.

## 3. Stable v0.16 Rust SDK documentation

- **Source:** `0xMiden/rust-sdk`, tag `v0.16.0`, commit `4e8407b9fa1e21e26eeb3040c915737a1293bde0`
- **Status:** `LOCAL_FIX_VALIDATED`, `NOT_SUBMITTED`
- **Finding:** Stable documentation pins `0.16.0-alpha.1` and includes stale authentication construction beside a stable 0.16.0 workspace.
- **Fix:** Pin the stable crate and align authentication examples with the tagged component API.
- **Validation:** Tagged-source comparison and local diff check passed.

The nested Turnkey and Para examples remain `MAINTAINER_INTENT_REQUIRED`; their older SDK families may be deliberate network pins and are not represented as confirmed defects.
