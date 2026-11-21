# Context: src

Owns domain policy, business invariants, transition judging, state reduction and learning-record interpretation. Does not create a second physical controller. TransitionVerdict (MapTransition compatibility alias) / node_transition is the implemented page-verdict slice; unified Observation/LaunchSpec/executor and evidence reservation remain migration work. Do not silently adapt pending into sent/accepted or reinterpret coin/module units.

Canonical definitions: [Wiki1.2](../../docs/wiki/zh_cn/1-overview.md#glossary). Accepted architecture: [ADR-0001](../../docs/adr/0001-runtime-convergence.md). Local synonyms must link to this dictionary, not redefine it. These are ownership boundaries, not workflow locks.

Mirror Agent source now wires EvidenceCapacity ahead of main-plan intent and direct native dispatch; fixed-size metadata slots account only for storage, never input/transaction success. See [Wiki6.8.1](../../docs/wiki/zh_cn/6-deployment.md#feature-6-8-1). General child-node/other-task/CLI coverage and whole-run capacity remain unaccepted.
