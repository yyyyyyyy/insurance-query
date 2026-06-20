# Ontology v2 扩展提案

## 当前本体 (v1)

- 22 entities (Product:4, Coverage:6, Disease:5, Regulation:3, Rule:4)
- 26 relations
- 5 种 EntityType

## v2 扩展方案

### 新增实体类型

| EntityType | 示例 | 数量 | 优先级 |
|---|---|---|---|
| InsuranceCompany | 平安健康、人保健康 | 15 | CRITICAL |
| ClaimCondition | 住院理赔条件、重疾确诊条件 | 8 | HIGH |
| PremiumFactor | 年龄费率、性别费率、职业费率 | 4 | MEDIUM |
| ExclusionCategory | 既往症除外、高风险运动除外 | 6 | MEDIUM |

### 新增关系类型

| RelationType | 示例 | 数量 |
|---|---|---|
| belongs_to | Product → InsuranceCompany | 20 |
| requires | Coverage → ClaimCondition | 12 |
| applies_to | Regulation → Product | 10 |
| supersedes | Regulation → Regulation | 2 |

### v2 目标

- entities: 22 → 55+
- relations: 26 → 70+
- entity_types: 5 → 8
- relation_types: 5 → 8
