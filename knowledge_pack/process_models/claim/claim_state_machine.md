# Claim Lifecycle — 理赔全流程状态机

## 概述

本状态机定义了保险理赔从出险到赔款到账的完整执行流程。可作为 InsureQuery Runtime 中 `ToolAgent → EligibilityCheckTool` 和 `CompareTool` 的过程执行蓝图。

## 状态流转图

```
 idle
   │ [保险事故发生]
   ▼
 accident_occurred
   │ [报案 (48h内) / 超时报案]
   ▼
 claim_reported
   │ [在保障期内?]
   ▼
 coverage_verification ──[不在保障期]──→ claim_rejected
   │ [属于保险责任?]
   ▼
 liability_check ──[不属于保险责任]──→ claim_rejected
   │ [属于免责条款?]
   ▼
 exclusion_check ──[属于免责条款]──→ claim_rejected
   │ [不属于免责]
   ▼
 document_collection
   │ [提交理赔材料]
   ▼
 document_submitted
   ├──[材料完整]──→ document_review
   └──[材料不完整]──→ need_supplement ──[补件完成]──→ document_review
                          │
                          └──[撤回申请]──→ claim_withdrawn ★
 document_review
   │ [核定赔付 (30日内)]
   ▼
 claim_evaluated
   ├──[审核通过]──→ claim_approved ──[支付赔款(10日内)]──→ claim_paid ★
   └──[拒赔]──→ claim_rejected ──[提出申诉]──→ appeal
                                               ├──[通过]──→ claim_approved
                                               └──[驳回]──→ claim_rejected ★

★ = 终态
```

## 状态列表 (16)

| State | 含义 | 证据/法规 |
|---|---|---|
| idle | 未出险 | — |
| accident_occurred | 保险事故发生 | — |
| claim_reported | 已报案（通常48h内） | REG012（理赔服务规范） |
| coverage_verification | 保障期核验 | REG001-23（等待期≤180天） |
| liability_check | 责任认定 | DOC001-C002（保障条款） |
| exclusion_check | 免责核查 | DOC001-C007（免责条款） |
| document_collection | 材料收集 | REG012（理赔材料要求） |
| document_submitted | 材料已提交 | — |
| document_review | 材料审核中 | REG003-23（30日内核定） |
| need_supplement | 需补充材料 | REG003-23 |
| claim_evaluated | 理赔核定 | REG001-30 |
| claim_approved | 同意赔付 | REG003-23（10日内支付） |
| claim_rejected | 拒赔 | — |
| claim_paid ★ | 理赔款到账 | — |
| claim_withdrawn ★ | 撤回理赔 | — |
| appeal | 申诉中 | — |

## 决策节点 (5)

| 决策 | 问题 | 分支 |
|---|---|---|
| D_coverage | 事故是否在保障期间内？ | yes→liability_check / no→claim_rejected |
| D_liability | 事故是否属于保险责任范围？ | yes→exclusion_check / no→claim_rejected |
| D_exclusion | 事故是否属于免责条款？ | yes→claim_rejected / no→document_collection |
| D_docs | 理赔材料是否齐全？ | yes→document_review / no→need_supplement |
| D_evaluate | 是否符合赔付条件且金额合理？ | yes→claim_approved / no→claim_rejected |

## 本体映射

| 本体实体 | 映射关系 |
|---|---|
| ENT-P001~P004 (产品) | 保障范围/免责条款来源 |
| ENT-C001~C004 (保障) | 具体保障项对应理赔类型 |
| ENT-D001~D005 (疾病) | 重疾/轻症对应理赔触发条件 |
| ENT-RL001 (等待期) | coverage_verification 规则来源 |
| ENT-RL004 (如实告知) | 影响 claim_rejected 决策 |
| ENT-R001 (健康保险管理办法) | 等待期/核定时限 |
| ENT-R003 (保险法) | 理赔时效/合同解除权 |

## 知识包证据映射

| 决策 | 证据来源 |
|---|---|
| D_coverage | `REG001`(健康保险管理办法), `PRODUCT.waiting_period_days` |
| D_liability | `DOC001-C002/C003`, `DOC002-C002/C005` (条款原文) |
| D_exclusion | `DOC001-C007`, `DOC002-C006` (免责条款) |
| D_docs | `REG012`(理赔规范), `REG003-23`(保险法) |
| D_evaluate | `REG001-30`(理赔服务标准), `PRODUCT.coverage_limit` |

## 可执行问句示例

InsureQuery Runtime 应能回答：
- "出险后应该什么时候报案？" → `E_report` + `REG012`
- "XX病属于e生保的保障范围吗？" → `D_liability` + `DOC001-C003`
- "理赔材料不齐怎么办？" → `need_supplement` + `REG012`
- "保险公司多久必须核定理赔？" → `D_docs` + `REG003-23`
- "拒赔了还能申诉吗？" → `appeal` + `REG003`

## 已知缺口

1. ❌ 申诉→仲裁→诉讼子流程未建模
2. ❌ 第三方责任追偿（代位求偿）未建模
3. ❌ 小额快赔通道未区分
4. ❌ 异地就医理赔流程未建模
