# 公开文件采集

从**保司官网**和**监管网站**下载公开文件。采集与导入分离，采集后需执行 `ingest_documents.py`。

```bash
python scripts/fetch_documents.py --init
python scripts/fetch_documents.py --regulations
python scripts/fetch_documents.py --products
python scripts/fetch_documents.py --all

# 采集完成后
python scripts/ingest_documents.py --all
```

完整说明见 [DATA.md](../DATA.md)。
