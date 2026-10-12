# Official Web SDK wallet lockfile demo

This deterministic fixture preserves the relevant dependency facts from
`0xMiden/web-sdk` commit `029aba8c92562786e16c22fac9247c3c8d64f091`.
The current wallet example manifest declared `^0.17.3`, while its colocated
pnpm lockfile resolved the same packages to `0.14.5`.

Run `run_demo.ps1`. The focused gate fails the before snapshot with
`MIDEN016-SDK-002`, then passes the fixed snapshot. Because Miden Preflight is
invoked with the v0.16 testnet target, `MIDEN016-SDK-001` remains expected for
the fixed current/devnet 0.17 example and is deliberately reported separately.
