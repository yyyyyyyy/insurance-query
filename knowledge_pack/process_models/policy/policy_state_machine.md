# Policy Lifecycle — 保单全生命周期状态机

## 概述

本状态机定义了保险保单从投保到终止的完整生命周期。覆盖投保、核保（引用 Underwriting Lifecycle）、犹豫期、等待期、保障期、续保、终止等核心阶段。可作为 InsureQuery Runtime 中 `EligibilityCheckTool` + `CompareTool` 的过程执行蓝图。

## 状态流转图

```
 idle
   │ [提交投保]
   ▼
 application ──→ underwriting (子流程: Underwriting Lifecycle)
                   ├──[核保通过]──→ policy_issued
                   │                  │ [签收保单]
                   │                  ▼
                   │              cooling_off (犹豫期 ≥15日)
                   │                ├──[犹豫期退保]──→ surrendered ★
                   │                └──[犹豫期满]──→ waiting_period (等待期 ≤180日)
                   │                                     │ [等待期满]
                   │                                     ▼
                   │                                  active (保障中)
                   │                                    ├──[保费到期]──→ premium_due
                   │                                    │                  ├──[缴费]──→ active ↩
                   │                                    │                  └──[逾期]──→ grace_period (宽限期)
                   │                                    │                                  ├──[补缴]──→ active ↩
                   │                                    │                                  └──[宽限期过]──→ lapsed
                   │                                    │                                                      │
                   │                                    │                                            reinstatement (复效中)
                   │                                    │                                              ├──[通过]──→ active ↩
                   │                                    │                                              └──[拒绝]──→ terminated ★
                   │                                    │
                   │                                    ├──[退保]──→ surrendered ★
                   │                                    ├──[理赔后终止]──→ terminated ★
                   │                                    ├──[期满]──→ fully_matured ★
                   │                                    └──[续保评估]──→ renewal_due
                   │                                                        ├──[保证续保]──→ renewed ──→ waiting_period ↩
                   │                                                        ├──[同意续保]──→ renewed ──→ waiting_period ↩
                   │                                                        └──[拒绝续保]──→ terminated ★
                   │
                   └──[核保拒保]──→ terminated ★
```

★ = 终态　　↩ = 循环回保障状态

## 状态列表 (17)

| State | 含义 | 子流程/法规 |
|---|---|---|
| idle | 未投保 | — |
| application | 投保中 | — |
| underwriting | 核保中 | → Underwriting Lifecycle |
| policy_issued | 保单签发 | — |
| cooling_off | 犹豫期 | REG001-15（≥15日） |
| waiting_period | 等待期 | REG001-23（≤180日） |
| active | 保障中 | — |
| premium_due | 保费应缴 | — |
| grace_period | 宽限期 | REG003（通常60日） |
| renewal_due | 续保评估 | REG001-17（保证续保定义） |
| renewed | 已续保 | → waiting_period |
| lapsed | 失效 | — |
| reinstatement | 复效中 | — |
| surrendered ★ | 退保 | — |
| terminated ★ | 终止 | — |
| fully_matured ★ | 满期 | — |
| policy_loan | 保单贷款 | （仅建模状态，未建模流程） |

## 决策节点 (4)

| 决策 | 问题 | 分支 | 法规依据 |
|---|---|---|---|
| D_cooling | 犹豫期内是否退保？ | 是→surrendered(全额退费) / 否→waiting_period | REG001-15 |
| D_waiting | 事故是否发生在等待期内（非意外）？ | 是→不赔付 / 否→正常赔付 | REG001-23 |
| D_renewal | 是否为保证续保产品？ | 是→自动续保 / 否→人工评估 | REG001-17 + PRODUCT.is_guaranteed_renewal |
| D_grace | 宽限期内是否补缴保费？ | 是→active / 否→lapsed | REG003 |

## 本体映射

| 本体实体 | 映射关系 |
|---|---|
| ENT-P001~P004 | 产品保证续保属性来源 |
| ENT-C006 (保证续保) | D_renewal 判定基准 |
| ENT-RL001 (等待期) | waiting_period state 规则 |
| ENT-RL003 (犹豫期) | cooling_off state 规则 |
| ENT-R001 (健康保险管理办法) | 犹豫期/等待期/保证续保法规 |
| ENT-R003 (保险法) | 宽限期/合同解除规则 |

## 知识包证据映射

| 决策 | 证据来源 |
|---|---|
| D_cooling | `REG001-15`（犹豫期≥15日） |
| D_waiting | `REG001-23`（等待期≤180日）, `PRODUCT.waiting_period_days` |
| D_renewal | `REG001-17`（保证续保定义）, `PRODUCT_CATALOG.is_guaranteed_renewal` + `guaranteed_renewal_years` |
| D_grace | `REG003`（保险法宽限期规定） |

## 可执行问句示例

- "保单犹豫期多少天？" → `cooling_off` + `REG001-15`
- "等待期内出险赔不赔？" → `D_waiting` + `REG001-23`
- "XX产品是保证续保的吗？" → `D_renewal` + `PRODUCT.is_guaranteed_renewal`
- "保费忘了交怎么办？" → `grace_period` + `REG003`
- "保单失效了还能恢复吗？" → `reinstatement`
- "续保会被拒吗？" → `D_renewal` + `REG001-17`

## 已知缺口

1. ❌ 保单贷款子流程未建模（仅状态占位）
2. ❌ 减额交清/保费自动垫交等特殊处理未建模
3. ❌ 受益人变更流程未建模
4. ❌ 保单批改（信息变更）流程未建模
5. ❌ 短期险(1年期)与长期险续保路径未区分
6. ❌ 保证续保产品 vs 非保证续保产品冷热期差异未细化
