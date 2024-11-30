# Support Milvus Sparse Vector CRUD Design

## 版本信息
- **创建日期**：2024-11-22
- **最后更新**: 2024-11-28
- **作者**: yanglh
- **版本**: v1.0

## 设计简要

> 背景
 
Dify默认使用的是weaviate向量数据库，该款数据库针对内容检索支持向量检索和全文检索两种方式，
但是由于国内信创要求，研发和生产环境向量数据库将会切换到国产向量数据库milvus，但是milvus2.4.x版本暂时
不支持类似于BM25算法的全文检索，因此需要设计相关功能来满足混合检索的需求。

> 思路

本设计主要是想通过修改dify的rag组件中milvus vdb部分的逻辑，使其支持混合检索，具体的方式就是通过支持sparse向量的CRUD，来完成多路检索的功能。

## 设计动机

本设计的初衷是因为业内实践以及我们自己的实地测试，证明了混合检索相较于单独的向量和全文检索拥有更好的鲁棒性和准确性，但是
dify自身的混合检索是通过通过组合向量检索和全文检索而实现的，而其中milvus部分的全文检索dify并未实现，因此我们决定完成这个部分。

## 设计目标

- 支持知识库上传至milvus后能够同时写入dense和sparse两种类型的向量

## 非目标

暂无


## 提案

> 提案思路

由于dify代码抽象了embedding行为以及创建、修改document的逻辑，因此，当我们需要sparse向量的时候，我们希望能够通过代理的方式将embedding请求转发至
内部模型接口上，并修改document的crud逻辑，在milvus模块中增加相应的sparse向量的支持。


## 具体设计

### sparse向量获取和生成

![sparse_vector获取](./images/dify-rag-proxy.png)

关于sparse向量的获取，我们选择了调用内部的创新实验室的LLM接口分别获取sparse模型信息和具体的
lexical_weights字段，并经过自行处理得到稀疏矩阵。

其中得到稀疏矩阵的逻辑为：
- 遍历 embedding_result["data"] 中的每个嵌入结果 emb。
- 初始化一个空列表 sparsest，用于存储当前嵌入结果的稀疏矩阵。
- 遍历 emb["embedding"]["sparse"] 中的每个稀疏向量 sparse_vec。
  - 将 sparse_vec 的键（indices）转换为整数列表 indices。
  - 将 sparse_vec 的值转换为 np.float64 类型的 NumPy 数组 values。
  - 创建一个与 indices 长度相同的 row_indices 列表，所有元素都为 0。
  - 使用 csr_array 创建一个稀疏矩阵 csr，形状为 (1, sparse_dim)。
  - 将 csr 添加到 sparsest 列表中。
- 将 sparsest 列表中的所有稀疏矩阵垂直堆叠（vstack），并转换为 CSR 格式（tocsr），然后添加到 sparse_embeddings 列表中。

## 变更历史

> v1.0变更
```text
# api/core代码变更
modified:   core/rag/datasource/retrieval_service.py
modified:   core/rag/datasource/vdb/field.py
modified:   core/rag/datasource/vdb/milvus/milvus_vector.py
modified:   core/rag/datasource/vdb/vector_base.py
modified:   core/rag/datasource/vdb/vector_factory.py

# api/service代码变更
modified:   services/model_proxy/__init__.py
modified:   services/model_proxy/http_proxy.py

# configs 增加自定义配置
modified:   configs/app_config.py
modified:   configs/custom/__init__.py
modified:   configs/custom/cffex_rag_model_config.py

# 文档变更
modified:   docs/Support Milvus Sparse Vector Design.md

modified:   pyproject.toml
```