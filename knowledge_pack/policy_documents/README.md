# 条款文件目录

存放**产品条款** PDF/TXT（采集或手动下载）。

导入命令见 [DATA.md](../DATA.md)：

```bash
python scripts/ingest_documents.py --init
python scripts/ingest_documents.py --all
```

文件名与 `manifest.json` 中 `file` 字段一致。可为某产品设置 `fetch_url` 指定条款 PDF 直链（供 `fetch_documents.py` 使用）。
