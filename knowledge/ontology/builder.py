"""
Ontology Builder — Populates the OntologyGraph from product catalog and ingested documents.

Loads entities from Sprint 2 data and links them to evidence chunks.
"""

from knowledge.ontology.graph import OntologyGraph, OntologyEntity, OntologyRelation, EntityType, RelationType

def build_insurance_ontology() -> OntologyGraph:
    g = OntologyGraph()

    # --- Products ---
    g.add_entity(OntologyEntity("ENT-P001","e生保·百万医疗",EntityType.PRODUCT,
        aliases=["e生保","e生保百万医疗"],
        properties={"product_type":"医疗险","company":"平安健康","guaranteed_renewal":False}))
    g.add_entity(OntologyEntity("ENT-P002","好医保·长期医疗",EntityType.PRODUCT,
        aliases=["好医保","好医保长期医疗"],
        properties={"product_type":"医疗险","company":"人保健康","guaranteed_renewal":True,
                     "guaranteed_renewal_years":20}))
    g.add_entity(OntologyEntity("ENT-P003","平安福·重疾险",EntityType.PRODUCT,
        aliases=["平安福","平安福重疾险"],
        properties={"product_type":"重疾险","company":"平安人寿"}))
    g.add_entity(OntologyEntity("ENT-P004","微医保·百万医疗",EntityType.PRODUCT,
        aliases=["微医保"],
        properties={"product_type":"医疗险","company":"泰康在线"}))

    # --- Diseases ---
    g.add_entity(OntologyEntity("ENT-D001","恶性肿瘤",EntityType.DISEASE,
        aliases=["癌症","肿瘤"],properties={"category":"重大疾病"}))
    g.add_entity(OntologyEntity("ENT-D002","急性心肌梗塞",EntityType.DISEASE,
        aliases=["心肌梗塞","心梗","心脏病发作"],properties={"category":"重大疾病"}))
    g.add_entity(OntologyEntity("ENT-D003","脑中风后遗症",EntityType.DISEASE,
        aliases=["脑中风","中风后遗症","中风"],properties={"category":"重大疾病"}))
    g.add_entity(OntologyEntity("ENT-D004","冠状动脉搭桥术",EntityType.DISEASE,
        aliases=["冠脉搭桥","搭桥手术"],properties={"category":"重大疾病"}))
    g.add_entity(OntologyEntity("ENT-D005","糖尿病",EntityType.DISEASE,
        aliases=["II型糖尿病"],properties={"category":"慢性病"}))

    # --- Coverages ---
    g.add_entity(OntologyEntity("ENT-C001","住院医疗保险金",EntityType.COVERAGE,
        aliases=["住院医疗","住院保障"]))
    g.add_entity(OntologyEntity("ENT-C002","重大疾病保险金",EntityType.COVERAGE,
        aliases=["重疾保障","重疾赔付"]))
    g.add_entity(OntologyEntity("ENT-C003","门诊手术医疗保险金",EntityType.COVERAGE,
        aliases=["门诊手术","门诊保障"]))
    g.add_entity(OntologyEntity("ENT-C004","轻度疾病保险金",EntityType.COVERAGE,
        aliases=["轻症保障","轻症"]))
    g.add_entity(OntologyEntity("ENT-C005","身故保险金",EntityType.COVERAGE,
        aliases=["身故保障","死亡赔付"]))
    g.add_entity(OntologyEntity("ENT-C006","保证续保",EntityType.COVERAGE,
        aliases=["保证续保条款","续保保障"],
        properties={"category":"续保条款"}))

    # --- Regulations ---
    g.add_entity(OntologyEntity("ENT-R001","健康保险管理办法",EntityType.REGULATION,
        aliases=["健康险管理办法"],
        properties={"issuer":"银保监会","year":2019}))
    g.add_entity(OntologyEntity("ENT-R002","重疾定义使用规范",EntityType.REGULATION,
        aliases=["重疾定义规范","重疾定义"],
        properties={"issuer":"中国保险行业协会","year":2020}))
    g.add_entity(OntologyEntity("ENT-R003","中华人民共和国保险法",EntityType.REGULATION,
        aliases=["保险法"],
        properties={"issuer":"全国人大常委会","year":2015}))

    # --- Rules (key insurance concepts) ---
    g.add_entity(OntologyEntity("ENT-RL001","等待期",EntityType.RULE,
        aliases=["等待期规则"],properties={"max_days":180,"regulation":"ENT-R001"}))
    g.add_entity(OntologyEntity("ENT-RL002","免赔额",EntityType.RULE,
        aliases=["免赔额规则","起付线"]))
    g.add_entity(OntologyEntity("ENT-RL003","犹豫期",EntityType.RULE,
        aliases=["冷静期"],properties={"min_days":15,"regulation":"ENT-R001"}))
    g.add_entity(OntologyEntity("ENT-RL004","如实告知",EntityType.RULE,
        aliases=["如实告知义务","健康告知"],properties={"regulation":"ENT-R003"}))

    # --- Relations ---
    # Coverage contained in products
    for cc, pp in [("ENT-C001","ENT-P001"),("ENT-C002","ENT-P001"),("ENT-C003","ENT-P001"),
                    ("ENT-C001","ENT-P002"),("ENT-C002","ENT-P002")]:
        g.add_relation(OntologyRelation(pp, cc, RelationType.CONTAINS))
    g.add_relation(OntologyRelation("ENT-P003","ENT-C002",RelationType.CONTAINS))
    g.add_relation(OntologyRelation("ENT-P003","ENT-C004",RelationType.CONTAINS))
    g.add_relation(OntologyRelation("ENT-P003","ENT-C005",RelationType.CONTAINS))

    # Products cover diseases
    for dd in ["ENT-D001","ENT-D002","ENT-D003"]:
        g.add_relation(OntologyRelation("ENT-P001", dd, RelationType.COVERS))
        g.add_relation(OntologyRelation("ENT-P002", dd, RelationType.COVERS))
    g.add_relation(OntologyRelation("ENT-P001","ENT-D004",RelationType.COVERS))
    g.add_relation(OntologyRelation("ENT-P003","ENT-D001",RelationType.COVERS))
    g.add_relation(OntologyRelation("ENT-P003","ENT-D002",RelationType.COVERS))

    # Regulations define rules
    g.add_relation(OntologyRelation("ENT-R001","ENT-RL001",RelationType.DEFINES))
    g.add_relation(OntologyRelation("ENT-R001","ENT-RL003",RelationType.DEFINES))
    g.add_relation(OntologyRelation("ENT-R003","ENT-RL004",RelationType.DEFINES))

    # Products regulated by regulations
    g.add_relation(OntologyRelation("ENT-P001","ENT-R001",RelationType.REGULATED_BY))
    g.add_relation(OntologyRelation("ENT-P002","ENT-R001",RelationType.REGULATED_BY))
    g.add_relation(OntologyRelation("ENT-P003","ENT-R002",RelationType.REGULATED_BY))

    # Disease defined by regulation
    g.add_relation(OntologyRelation("ENT-D001","ENT-R002",RelationType.DEFINES))

    # Guaranteed renewal
    g.add_relation(OntologyRelation("ENT-P002","ENT-C006",RelationType.CONTAINS))
    g.add_relation(OntologyRelation("ENT-R001","ENT-C006",RelationType.DEFINES))

    return g
