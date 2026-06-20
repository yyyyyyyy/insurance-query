# Underwriting Lifecycle — 核保全流程状态机

## 概述

本状态机定义了保险核保从投保申请到承保决定的完整执行流程。可作为 InsureQuery Runtime 中 `EligibilityCheckTool` 的过程执行蓝图。

## 状态流转图

```
 idle
   │ [提交投保申请]
   ▼
 application_submitted
   │ [健康告知]
   ▼
 health_declaration
   ├──[如实告知=是]──→ honesty_check
   │                      │ [风险评估]
   │                      ▼
   │               risk_assessment
   │                 ├──[标准体]──→ standard_risk ──[接受]──→ standard_accepted ★
   │                 ├──[次标准体]──→ substandard_risk
   │                 │                 ├──[加费→接受]──→ added_premium_accepted ★
   │                 │                 ├──[加费→拒绝]──→ exclusion_eval
   │                 │                 │                   ├──[除外→接受]──→ exclusion_accepted ★
   │                 │                 │                   └──[除外→拒绝]──→ declined ★
   │                 │                 └──[拒保]──→ declined ★
   │                 └──[转人工]──→ manual_review → (同上)
   │
   └──[不如实告知]──→ declined ★
```

★ = 终态

## 状态列表 (15)

| State | 含义 | 证据/法规 |
|---|---|---|
| idle | 未投保 | — |
| application_submitted | 投保申请已提交 | — |
| health_declaration | 健康告知 | REG003-16（如实告知义务） |
| honesty_check | 如实告知核查 | REG003-16 |
| risk_assessment | 风险评估 | PRODUCT.eligibility |
| standard_risk | 标准体 | — |
| substandard_risk | 次标准体 | — |
| standard_accepted ★ | 标准承保 | — |
| added_premium_eval | 加费评估 | REG001-21（费率确定） |
| added_premium_accepted ★ | 加费承保 | — |
| exclusion_eval | 除外评估 | — |
| exclusion_accepted ★ | 除外承保 | — |
| declined ★ | 拒保 | REG003-16 |
| application_withdrawn ★ | 撤回申请 | — |
| manual_review | 人工核保 | — |

## 决策节点 (4)

| 决策 | 问题 | 分支 | 法规依据 |
|---|---|---|---|
| D_honesty | 健康告知是否真实？ | 是→risk_assessment / 否→declined | REG003-16（合同成立超2年不得解除） |
| D_risk | 标准体还是次标准体？ | 标准→standard_accepted / 次标准→加费/除外/拒保 | PRODUCT.eligibility |
| D_premium | 投保人是否接受加费？ | 是→added_premium_accepted / 否→exclusion_eval | REG001-21 |
| D_exclusion | 投保人是否接受除外责任？ | 是→exclusion_accepted / 否→declined | — |

## 本体映射

| 本体实体 | 映射关系 |
|---|---|
| ENT-P001~P004 (产品) | eligibility规则来源 |
| ENT-RL004 (如实告知) | D_honesty 规则来源 |
| ENT-R001 (健康保险管理办法) | D_premium（费率规则） |
| ENT-R003 (保险法) | D_honesty（如实告知法律依据） |

## 知识包证据映射

| 决策 | 证据来源 |
|---|---|
| D_honesty | `REG003`(保险法16条), `DOC006-C001` |
| D_risk | `PRODUCT_CATALOG.eligibility`（min_age/max_age/health_check_required）, `PRODUCT_CATALOG.exclusions` |
| D_premium | `REG001-21`(费率确定), `PRODUCT_CATALOG.premium_reference` |

## 可执行问句示例

- "有结节还能买百万医疗险吗？" → `D_risk` + `PRODUCT.eligibility`
- "不如实告知会怎样？" → `D_honesty` + `REG003-16`
- "XX产品最高投保年龄是多少？" → `D_risk` + `PRODUCT_CATALOG.eligibility.max_age`
- "加费承保是什么意思？" → `added_premium_eval` + `REG001-21`
- "除外承保哪些情况会出现？" → `exclusion_eval` + `PRODUCT.exclusions`

## 已知缺口

1. ❌ 健康告知问题库未建模（每个产品有特定的健康告知问题列表）
2. ❌ 智能核保规则引擎未实现（结节分级/高血压分期等条件规则）
3. ❌ 职业类别风险评估未建模
4. ❌ 财务核保路径未建模
5. ❌ 体检核保子路径未区分
