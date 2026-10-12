# Architecture and evidence boundaries

```mermaid
flowchart LR
    Repo[Repository] --> Role[Role detector]
    Role --> Target[Target/profile resolver]
    Target --> Rules[Static rules]
    Rules --> Checks[Dependencies · MASM · APIs · stores]
    Checks --> Evidence[Semantic evidence]
    Live[Optional owner-gated live lane] -. public evidence .-> Evidence
    Evidence --> Results[Text · JSON · SARIF · CI]
```

Every rule carries role applicability metadata. Semantic assertions carry a proof type, and unsupported behavior remains `REVIEW_REQUIRED`. The default path is local, static, and read-only.
