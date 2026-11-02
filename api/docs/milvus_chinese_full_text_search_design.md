# Milvus 中文全文检索设计文档

## 背景

Dify 当前通过向量数据库承载知识库索引与检索。Milvus 在 2.5.0 之后支持基于 BM25 的全文检索能力：写入原始文本后，Milvus 可以通过内置 BM25 Function 将文本字段转换为稀疏向量，并在检索时使用 BM25 评分。

此前实现中，Milvus 全文检索使用默认 analyzer。默认 analyzer 对英文场景可用，但对中文文本通常无法得到符合预期的分词结果，导致中文全文检索召回效果较弱。为了支持中文知识库的 BM25 检索，需要允许部署方配置 Milvus text analyzer，例如：

```env
MILVUS_ANALYZER_PARAMS={"type":"chinese"}
```

## 目标

1. 支持通过环境变量配置 Milvus analyzer 参数。
2. 在新建 Milvus collection 时，将 analyzer 参数写入文本字段 schema。
3. 保持默认行为不变：未配置 analyzer 参数时继续使用 Milvus 默认 analyzer。
4. 保持向后兼容：低版本 Milvus 或关闭 hybrid search 时，不启用 BM25 全文检索相关 schema。

## 非目标

1. 不改造前端知识库配置页面。
2. 不对已有 Milvus collection 原地变更 analyzer。Milvus 字段 schema 建立后不可按当前实现自动迁移。
3. 不改变 Dify 现有混合检索、重排序和 score threshold 的整体流程。
4. 不提供跨向量库的统一 analyzer 配置抽象，本设计只覆盖 Milvus。

## 配置设计

新增配置项：

```env
MILVUS_ANALYZER_PARAMS=
```

推荐中文 BM25 配置：

```env
MILVUS_ANALYZER_PARAMS={"type":"chinese"}
```

配置入口位于 `api/configs/middleware/vdb/milvus_config.py`：

- `MILVUS_ANALYZER_PARAMS` 类型为字符串。
- 默认值为空字符串，表示不显式设置 analyzer。
- 配置描述说明该参数用于 Milvus full-text search。

运行时配置模型位于 `api/core/rag/datasource/vdb/milvus/milvus_vector.py`：

- `MilvusConfig.analyzer_params` 接收 `dict[str, Any] | str | None`。
- 如果传入字符串，先 `strip()`。
- 空字符串转换为 `None`。
- 非空字符串必须是合法 JSON；非法 JSON 抛出配置校验错误。
- 合法 JSON 会被解析为 Python dict，并在创建 schema 时传给 pymilvus。

## 索引创建流程

Milvus collection 创建发生在 `MilvusVector.create_collection()`。

新建 collection 时会创建以下字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `metadata` | JSON | 文档元数据 |
| `text` | VARCHAR | 原始文本内容 |
| `id` | INT64 | Milvus auto id 主键 |
| `vector` | FLOAT_VECTOR 或其他 embedding 类型 | 语义向量 |
| `sparse_vector` | SPARSE_FLOAT_VECTOR | BM25 稀疏向量，仅 hybrid search 开启且版本支持时创建 |

当 hybrid search 可用时，文本字段 schema 形态如下：

```python
text_field_kwargs = {
    "max_length": 65_535,
    "enable_analyzer": True,
}

if analyzer_params:
    text_field_kwargs["analyzer_params"] = analyzer_params

FieldSchema("text", DataType.VARCHAR, **text_field_kwargs)
```

同时创建 BM25 Function：

```python
Function(
    name="text_bm25_emb",
    input_field_names=["text"],
    output_field_names=["sparse_vector"],
    function_type=FunctionType.BM25,
)
```

写入文档时，Dify 只写入原始文本、dense vector 和 metadata；不直接写入 sparse vector。Milvus 根据 BM25 Function 自动从文本字段生成稀疏向量。

## 检索流程

### 全文检索

`MilvusVector.search_by_full_text()` 负责 BM25 检索：

1. 检查 hybrid search 是否启用。
2. 检查 collection 是否存在 `sparse_vector` 字段。
3. 使用 query 原文作为 `data=[query]`。
4. 指定 `anns_field="sparse_vector"`。
5. 返回 `text` 和 `metadata`。
6. 复用 `_process_search_results()` 写入 `metadata["score"]` 并过滤 score threshold。

当 Milvus 版本低于 2.5.0、显式关闭 `MILVUS_ENABLE_HYBRID_SEARCH`，或 collection 中不存在 `sparse_vector` 字段时，全文检索返回空列表并记录 warning。

### 混合检索

Dify 上层混合检索仍沿用已有流程：向量检索和全文检索分别执行，之后由上层 retrieval/rerank 流程合并和重排。本设计只影响 Milvus 全文检索中的 analyzer 行为，不改变混合检索排序策略。

## 兼容性设计

### Milvus 版本

Milvus BM25 / full-text search 能力要求 Milvus 版本不低于 2.5.0。运行时通过 `get_server_version()` 判断：

- `>= 2.5.0`：允许创建 BM25 sparse vector 字段和 Function。
- `< 2.5.0`：关闭 hybrid search，collection 只创建 dense vector 相关字段。
- 版本检查失败：记录 warning 并关闭 hybrid search。

### 默认配置

`MILVUS_ANALYZER_PARAMS` 默认为空，不改变已有英文或默认 analyzer 使用方式。

### 已有 collection

analyzer 参数只在创建 collection schema 时生效。已有 collection 的文本字段 schema 不会被自动修改，因此：

- 对已有知识库，修改 `MILVUS_ANALYZER_PARAMS` 后不会自动生效。
- 如需应用新的 analyzer，需要重建对应知识库索引或删除后重建 Milvus collection。
- 这避免了运行时对已有数据结构做隐式迁移，降低数据风险。

## 错误处理

配置校验阶段处理 JSON 格式错误：

```env
MILVUS_ANALYZER_PARAMS={invalid
```

会触发：

```text
config MILVUS_ANALYZER_PARAMS must be a valid JSON object
```

运行期如果 Milvus 不支持 BM25 或 collection schema 不包含 `sparse_vector`，全文检索不会抛出异常，而是返回空结果，保持上层检索流程可继续执行。

## 部署方式

Docker 环境在 `docker/.env.example` 和 `docker/docker-compose.yaml` 中增加配置透传：

```env
MILVUS_ENABLE_HYBRID_SEARCH=True
MILVUS_ANALYZER_PARAMS={"type":"chinese"}
```

注意事项：

1. Milvus 服务版本需要不低于 2.5.0。
2. analyzer 参数必须是合法 JSON。
3. 配置只影响新建 collection。
4. 若环境变量中 JSON 需要额外转义，应以实际部署平台的 env 规则为准。

## 测试设计

单元测试覆盖 `MilvusConfig` 的 analyzer 参数解析：

1. `analyzer_params='{"type":"chinese"}'` 被解析为 `{"type": "chinese"}`。
2. `analyzer_params="{invalid"` 触发配置校验错误。
3. 既有必填配置校验保持不变。

建议补充的集成测试：

1. 使用 Milvus 2.5.0 及以上版本启动测试环境。
2. 配置 `MILVUS_ENABLE_HYBRID_SEARCH=True` 和 `MILVUS_ANALYZER_PARAMS={"type":"chinese"}`。
3. 创建包含中文文本的知识库并写入文档。
4. 执行全文检索，验证中文 query 能命中中文文档。
5. 验证新建 collection 的 `text` 字段包含预期 analyzer params，且存在 BM25 Function 与 `sparse_vector` 字段。

## 风险与限制

1. analyzer 配置错误会导致 collection 创建失败或检索效果不符合预期。
2. 不同 Milvus 版本支持的 analyzer 参数可能存在差异，需要以部署版本的 Milvus 文档为准。
3. 已有 collection 不会自动迁移，配置变更需要重建索引。
4. 当前实现只校验 JSON 格式，不校验 analyzer 参数语义。
5. 中文 analyzer 会改善中文 BM25 召回，但最终混合检索效果仍受 chunk 切分、query 表达、BM25 评分、向量召回和 rerank 策略共同影响。

## 相关代码

- `api/configs/middleware/vdb/milvus_config.py`
- `api/core/rag/datasource/vdb/milvus/milvus_vector.py`
- `api/tests/unit_tests/core/rag/datasource/vdb/milvus/test_milvus.py`
- `docker/.env.example`
- `docker/docker-compose.yaml`
