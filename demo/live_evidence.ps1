$ErrorActionPreference = "Stop"
$profile = Get-Content -Raw (Join-Path $PSScriptRoot "..\profiles\miden-testnet-0.17.1.json") | ConvertFrom-Json
$tx = $profile.post_validation
$note = $profile.private_note_discovery

Write-Output "MIDEN TESTNET LIVE EVIDENCE (READ-ONLY)"
Write-Output "Network: $($profile.network.name) $($profile.network.version)"
Write-Output "Transaction: $($tx.canonical_transaction_id)"
Write-Output "Block: $($tx.block_number)"
Write-Output "Transfer: $($tx.transfer_amount)"
Write-Output "Actual fee: $($tx.actual_fee)"
Write-Output "Private note: CREATED / COMMITTED / DELIVERED / DISCOVERED / CONSUMABLE"
Write-Output "Consumption: intentionally not executed (fee unavailable before Accept)"
Write-Output "Proof source: public chain metadata plus owner-provided Bread UI evidence"
