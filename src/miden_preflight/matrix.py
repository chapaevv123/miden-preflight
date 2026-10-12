TARGET = "miden-0.16"

VERSION_MATRIX = {
    "target": TARGET,
    "network": {
        "testnet": "0.16",
        "devnet": "0.17",
    },
    "protocol_client": "0.16",
    "web_sdk": "0.16",
    "react_sdk": "0.16",
    "vm_crypto": "0.29",
    "midenup_toolchain": "0.16",
    "rust": "1.98.1",
    "contract_sdk_rust": "1.99",
    "release_policy": "Do not mix 0.16 release candidates and stable artifacts.",
    "source": "https://docs.miden.xyz/builder/migration/",
}

VM_CRATES = {
    "miden-assembly", "miden-core", "miden-core-lib", "miden-processor",
    "miden-prover", "miden-verifier", "miden-crypto",
}


def expected_family(package: str) -> str | None:
    if package.startswith("@miden-sdk/"):
        return "0.16"
    if package in VM_CRATES:
        return "0.29"
    if package.startswith("miden-") and package not in {"miden", "midenc", "miden-stdlib"}:
        return "0.16"
    return None
