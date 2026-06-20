# Insurance World Model — Coverage Report

**生成日期**: 2026-06-20
**建模范围**: Claim Lifecycle, Underwriting Lifecycle, Policy Lifecycle

---

## 核心问题

> **InsureQuery 是否可以模拟一次真实的保险理赔/核保/保单生命周期过程？**

---

## 答案: 部分可以

### 当前可模拟的场景 ✅

| 场景 | 状态 | 证据 |
|---|---|---|
| **标准理赔流程** (报案→核验→审核→赔付) | ✅ 可模拟 | 16 states + 5 decisions，所有关键节点已建模 |
| **标准核保流程** (告知→评估→标准/加费/除外/拒保) | ✅ 可模拟 | 15 states + 4 decisions |
| **保单犹豫期/等待期逻辑** | ✅ 可模拟 | 法规驱动的冷却/等待判断 |
| **保证续保 vs 非保证续保决策** | ✅ 可模拟 | 基于 PRODUCT.is_guaranteed_renewal |
| **保费逾期→宽限期→失效流程** | ✅ 可模拟 | grac_period + lapsed + reinstatement |

### 当前不可模拟的场景 ❌

| 场景 | 缺失内容 | 严重度 |
|---|---|---|
| **拒赔后申诉→仲裁→诉讼** | appeal state 存在但无下游路径 | HIGH |
| **理赔材料具体内容核验** | 只知道"材料是否齐全"但不知道需要哪些材料 | HIGH |
| **特定疾病的赔付条件判断** | 只有疾病实体名称，无疾病定义/赔付标准文本 | HIGH |
| **智能核保: 结节/高血压分级** | 无健康告知问题库和规则引擎 | HIGH |
| **第三方责任追偿** | 完全缺失 | MEDIUM |
| **小额快赔通道** | 完全缺失 | MEDIUM |
| **保单贷款流程** | 仅状态占位 | MEDIUM |
| **异地就医理赔** | 完全缺失 | MEDIUM |
| **受益人变更/保单批改** | 完全缺失 | LOW |
| **长期险 vs 短期险续保差异** | 当前模型混用 | LOW |

---

## 三个过程的完整度评估

### Claim Lifecycle — 完整度: 70%

```
已建模 ✅    idle → accident → report → coverage_check → liability → exclusion → docs → review → evaluate → approve/reject → pay/appeal
缺失 ❌     appeal → 仲裁 → 诉讼
缺失 ❌     第三方责任追偿（代位求偿）
缺失 ❌     小额快赔通道
缺失 ❌     异地就医特殊流程
缺失 ❌     理赔材料具体清单（需从knowledge_pack补充）
```

### Underwriting Lifecycle — 完整度: 60%

```
已建模 ✅    idle → apply → health_declaration → honesty → risk → standard/substandard → accept/premium/exclusion/decline
缺失 ❌     健康告知问题库（每个产品的问题列表未结构化）
缺失 ❌     智能核保规则引擎（结节分级/高血压分期→承保条件映射）
缺失 ❌     职业类别→承保条件映射
缺失 ❌     财务核保路径
缺失 ❌     体检核保子路径
```

### Policy Lifecycle — 完整度: 65%

```
已建模 ✅    idle → apply → underwriting → issued → cooling_off → waiting → active → premium_due → grace → lapsed → reinstatement → terminated
已建模 ✅    active → renewal_due → renewed/terminated
缺失 ❌     保单贷款完整子流程
缺失 ❌     减额交清/保费自动垫交
缺失 ❌     受益人变更
缺失 ❌     保单批改（信息变更）
缺失 ❌     短期(1Y) vs 长期(20Y)续保路径分离
```

---

## 决策可结构化分析

| 决策 | 当前可否结构化 | 依赖 |
|---|---|---|
| D_coverage (是否在保障期内) | ✅ 可 | PRODUCT.waiting_period_days + 出险日期 |
| D_liability (是否属于保险责任) | ⚠️ 部分 | 需要条款文本中的疾病定义/赔付标准 |
| D_exclusion (是否免责) | ✅ 可 | PRODUCT.exclusions 列表 |
| D_docs (材料是否齐全) | ❌ 不可 | 需要理赔材料清单结构化数据 |
| D_honesty (是否如实告知) | ⚠️ 部分 | 需要健康告知问题库 |
| D_risk (标准体/次标准体) | ⚠️ 部分 | 需要核保规则引擎 |
| D_renewal (是否可续保) | ✅ 可 | PRODUCT.is_guaranteed_renewal |
| D_waiting (是否在等待期中) | ✅ 可 | PRODUCT.waiting_period_days + 事故日期 |
| D_grace (宽限期内是否补缴) | ✅ 可 | 日期计算 + 保费缴纳记录 |

**可结构化率: 5/9 (56%)** — 4个决策需要补充数据或规则引擎

---

## 知识包 → 过程模型映射验证

| 知识包资产 | 被 Claim 引用 | 被 UW 引用 | 被 Policy 引用 |
|---|---|---|---|
| products/catalog.json | ✅ (coverage, exclusions, waiting_period) | ✅ (eligibility, exclusions) | ✅ (is_guaranteed_renewal, waiting_period_days) |
| regulations/REG001 | ✅ (等待期, 理赔时限) | ✅ (费率确定) | ✅ (犹豫期, 等待期, 保证续保) |
| regulations/REG003 | ✅ (理赔时效, 合同解除) | ✅ (如实告知) | ✅ (宽限期, 合同解除) |
| regulations/REG012 | ✅ (理赔服务规范) | ❌ | ❌ |
| faq_dataset | ⚠️ 间接引用 | ⚠️ 间接引用 | ⚠️ 间接引用 |

**映射完整率: products 100%, regulations 75%, FAQ 0% (未直接映射)**

---

## 成功标准验证

### ✅ 达标项

1. ✅ 三个过程图全部构建完成（Claim 16S/19E/20T/5D, UW 15S/17E/20T/4D, Policy 17S/21E/25T/4D）
2. ✅ 每个状态/事件/迁移均有明确含义
3. ✅ 每个决策节点有 evidence_refs 和 ontology_mapping
4. ✅ 每个 process graph 有 ontology_mapping 章节
5. ✅ 每个 process graph 有 evidence_mapping + knowledge_pack 引用
6. ✅ 三条过程图之间可互引用（Policy→Underwriting 子流程，Claim→Policy 保障期）

### ❌ 未达标项

1. ❌ **无法端到端模拟一次包含具体疾病名称的完整理赔**
   - 原因: 缺少疾病定义/赔付标准条款文本
   
2. ❌ **无法模拟智能核保中的具体疾病风险评估**
   - 原因: 缺少健康告知问题库和核保规则引擎

3. ❌ **无法回答"理赔需要哪些具体材料"**
   - 原因: 理赔材料清单未结构化

---

## 推荐 — 使过程模型可执行的最低补充

按 ROI 排序：

| 优先级 | 补充内容 | 影响的过程 |
|---|---|---|
| **P0** | 健康告知问题库（结构化: 疾病→承保条件映射） | Underwriting D_risk |
| **P0** | 理赔材料清单（结构化: 理赔类型→所需材料） | Claim D_docs |
| **P1** | 疾病定义/赔付标准文本（从条款中提取） | Claim D_liability |
| **P1** | 申诉-仲裁-诉讼子流程完整建模 | Claim |
| **P2** | 智能核保规则引擎（结节/高血压分级逻辑） | Underwriting D_risk |
| **P2** | 第三方责任追偿子流程 | Claim |
| **P3** | 保单贷款流程完整建模 | Policy |
| **P3** | 小额快赔通道 | Claim |
| **P3** | 短期险 vs 长期险续保路径分离 | Policy |

---

## 最终结论

**InsureQuery 当前可以模拟保险过程的"骨架"（状态流转+核心决策），但无法模拟"血肉"（具体的疾病赔付条件、健康告知问题、理赔材料清单）。**

下一步最关键的补充不是更多产品数据，而是：
1. **结构化核保规则** — 将"结节→承保条件"这类隐性知识显式化为规则
2. **结构化理赔材料清单** — 将"需要哪些材料"从 FAQ 文本转化为结构化数据
3. **疾病赔付标准文本** — 将条款中的疾病定义摄入为可匹配的证据

这三项完成后，过程模型即可从"可展示"升级为"可执行"。
