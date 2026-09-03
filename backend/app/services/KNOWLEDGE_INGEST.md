# Knowledge ingest pipeline (ported from SolarSense)

## SolarSense 对照

| 步骤 | SolarSense | AgentForge（本目录） |
|------|------------|----------------------|
| 文档解析 / 轻清洗 | Python worker `TEXT_PARSE_DOCUMENT` | `doc_parse.py` |
| 规则清洗 | Python worker `TEXT_CLEAN` | `text_clean.py` |
| Token 切分 | Java `TokenTextSplitter` | `knowledge_chunk.chunk_text_by_token` |
| 向量 | Java → Milvus | `knowledge_vector.py`（本机 Milvus） |

## 入库 API

- 粘贴文本：`POST /api/v1/knowledge/bases/{id}/documents`
- 上传文件：`POST /api/v1/knowledge/bases/{id}/documents/upload`（multipart `file`）

`segment_max_chars` 字段在切分时按 **token 窗口大小**使用（对齐 Java `segmentMaxTokens`，默认 800）。
