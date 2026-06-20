# Insurance Decision Rule Engine — Coverage Report
**生成日期**: 2026-06-20
**规则总数**: 45 (UW=14, CL=13, EL=10, CI=8)
---

## 1. 规则覆盖 — 按决策域

| 域 | 规则数 | 覆盖主题 |
|---|---|---|
| **underwriting** | 14 | 告知义务, 恶性肿瘤核保, 心血管疾病核保, 高血压核保, 糖尿病核保, 结节核保, 职业风险评估, 年龄限制 |
| **claim** | 13 | 等待期判定, 保障范围, 免责条款, 免赔额, 材料审核, 重疾确诊条件, 理赔时效 |
| **eligibility** | 10 | 年龄资格, 健康告知资格, 职业资格, 既往症与除外, 保证续保资格, 身份证件核验 |
| **clause** | 8 | 疾病覆盖判定, 免责判定, 保证续保条款解释, 等待期条款解释, 门诊手术覆盖, 轻症赔付解释, 意外伤害条款 |

## 2. 决策覆盖

| 决策 | 支持该决策的规则数 |
|---|---|
| approve | 4 |
| conditional_eligible | 2 |
| covered | 4 |
| eligible | 5 |
| exclusion | 3 |
| extra_premium | 1 |
| not_covered | 2 |
| not_eligible | 3 |
| partial_approve | 3 |
| partially_covered | 2 |
| reject | 11 |
| request_more_docs | 1 |
| standard_accept | 4 |

## 3. Ontology Entity 覆盖

规则系统使用的 Ontology Entity: **27** 个

| Entity | 被引用次数 |
|---|---|
| ENT-P002 | 20 |
| ENT-P001 | 19 |
| ENT-P003 | 15 |
| ENT-D001 | 11 |
| ENT-R003 | 6 |
| ENT-D002 | 5 |
| ENT-P004 | 5 |
| ENT-D003 | 4 |
| ENT-D004 | 4 |
| ENT-RL004 | 3 |
| ENT-P013 | 3 |
| ENT-P014 | 3 |
| ENT-RL001 | 3 |
| ENT-R001 | 3 |
| ENT-C002 | 3 |
| ENT-C003 | 3 |
| ENT-C004 | 3 |
| ENT-C001 | 3 |
| ENT-C006 | 3 |
| ENT-D006 | 2 |
| ENT-P016 | 2 |
| ENT-P017 | 2 |
| ENT-D005 | 2 |
| ENT-RL002 | 2 |
| ENT-R002 | 2 |
| ENT-P015 | 1 |
| ENT-P004(类比) | 1 |

## 4. Process Layer 覆盖

规则系统覆盖的 Process Node: **13** 个

## 5. 缺口分析

### 5.1 当前规则系统无法覆盖的问题

- **理赔金额计算**: 无精算公式规则——如'扣除免赔额后按比例赔付'无法自动计算
- **申诉-仲裁-诉讼**: 无相关规则——appeal state 存在但 downstream rules 缺失
- **疾病严重度量化**: 缺少疾病严重度评分体系（如疾病分级ICD编码→赔付比例映射）
- **多产品交叉比较**: 规则只支持单产品决策，无法执行'A产品 vs B产品哪个更好'类型决策
- **等待期-既往症交互**: 既往症在等待期内发病 vs 等待期后发病的规则未分离
- **免赔额跨年度累计**: 部分产品支持年度累计免赔额，但规则中未区分单次 vs 累计

### 5.2 仍依赖"经验判断"的决策

| 决策 | 原因 |
|---|---|
| 加费幅度确定 | 不同产品对同一疾病的加费比例不同，缺少综合费率表 |
| 次标准体vs拒保边界 | 部分疾病（如轻度糖尿病）的承保决策因产品而异 |
| 理赔材料真实性审核 | 伪造病历/发票的检测依赖人工 |
| 复杂既往症的多次疾病关联评估 | 多个既往症组合的风险评估无量化模型 |

### 5.3 缺少规则支持的 Ontology Entity

| Entity | 类型 | 原因 |
|---|---|---|
| ENT-C005 (身故保险金) | C005 | 无直接规则引用 |
| ENT-RL003 (犹豫期) | RL003 | 无直接规则引用 |

## 6. 推荐 — 按优先级补充规则

| 优先级 | 规则类型 | 预期覆盖 |
|---|---|---|
| **P0** | 疾病严重度→赔付比例映射规则 (ICD→payout) | Claim D_liability 精确化 |
| **P0** | 理赔材料清单规则 (claim_type→required_docs) | Claim D_docs 可结构执行 |
| **P1** | 多既往症组合风险评估规则 | Underwriting D_risk 量化 |
| **P1** | 申诉-仲裁-诉讼决策规则 | Claim appeal→resolution |
| **P2** | 产品比较规则 (A vs B dimension scoring) | product_comparison 类查询 |
| **P2** | 免赔额累计/分摊规则 | Claim D_deductible 精确化 |
