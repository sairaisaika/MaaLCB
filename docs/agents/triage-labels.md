# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Wayfinder labels

`/wayfinder` uses one additional label family on the same tracker, with no role mapping — the label string is the type:

| Label              | Meaning                                                    |
| ------------------ | ---------------------------------------------------------- |
| `wayfinder:map`    | The map issue; owns Notes / Decisions so far / Fog          |
| `wayfinder:research` | Research ticket                                          |
| `wayfinder:prototype` | Prototype ticket                                        |
| `wayfinder:grilling` | Open decision / discussion ticket                       |
| `wayfinder:task`   | Task ticket                                                |

## 本仓库现状

这 10 枚标签（五角色 + 五 wayfinder）在远端 `sairaisaika/MaaLCB` 上还没有创建，第一次用到 issue 流程时
再建；`bug` 使用 GitHub 自带的那一枚。除技能明确要求外，不额外强制任何标签。
