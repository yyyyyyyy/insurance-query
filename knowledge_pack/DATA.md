# 数据采集与导入

> **当前状态**：知识包数据已清空，请从 `products/catalog.json` 和 `regulations/catalog.json` 开始整理。

仅两个入口，**采集与导入分离**：

| 步骤 | 命令 | 说明 |
|------|------|------|
| **采集** | `python scripts/fetch_documents.py` | 从保司官网、监管网站下载公开文件 |
| **导入** | `python scripts/ingest_documents.py` | 将本地 PDF/TXT 解析为检索 Chunk |

也可跳过采集，**自行下载文件**后放入对应目录再导入。

## 1. 采集（可选）

```bash
python scripts/fetch_documents.py --init
python scripts/fetch_documents.py --regulations   # 监管文件
python scripts/fetch_documents.py --products      # 保司官网
python scripts/fetch_documents.py --all
```

- 仅允许：catalog 中保司 `source_url` 域名 + `*.gov.cn` / `nfra.gov.cn` / `iachina.cn`
- 输出：`policy_documents/`、`regulations/documents/`

## 2. 导入（必须，才能有检索数据）

```bash
python scripts/ingest_documents.py --init          # 初始化产品 manifest
python scripts/ingest_documents.py --all           # 导入全部已有文件
python scripts/ingest_documents.py --list        # 查看状态
```

- 手动导入：将 PDF/TXT 放入 `policy_documents/` 或 `regulations/documents/`，再执行 `--all`
- 输出：`knowledge_pack/chunks/ingested_documents.json`（运行时唯一文档来源）

## 目录

```
knowledge_pack/
├── policy_documents/          # 产品条款（采集或手动）
│   └── manifest.json
├── regulations/
│   ├── catalog.json           # 法规元数据
│   ├── manifest.json          # 导入清单（fetch --init 生成）
│   └── documents/             # 法规正文（采集或手动）
└── chunks/
    └── ingested_documents.json  # 导入结果
```
