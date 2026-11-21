# Context: desktop

Owns configuration editing and resolving user intent into the launch boundary. TeamSlot, saved profile, preset and rotation cursor are different identifiers. Run count is independent of deployment count. GUI settings, effective launch intent and active-run binding must be reported separately; a UI edit cannot silently rebind a pending transaction.

Canonical definitions: [Wiki1.2](../../docs/wiki/zh_cn/1-overview.md#glossary). Accepted architecture: [ADR-0001](../../docs/adr/0001-runtime-convergence.md). Local synonyms must link to this dictionary, not redefine it. These are ownership boundaries, not workflow locks.
