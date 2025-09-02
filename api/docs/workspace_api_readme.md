# Remote Workspace API 文档

## 移动账户到租户接口

### 接口描述
此接口用于将一个用户账户移动到指定的租户下，支持设置用户在该租户中的角色。

### 接口信息
- **URL**: `/remote-api/workspace/move-account`
- **方法**: `POST`
- **Content-Type**: `application/json`

### 请求参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| account_id | string | 是 | - | 要移动的账户ID |
| tenant_id | string | 是 | - | 目标租户ID |
| role | string | 否 | normal | 用户在租户中的角色 |

### 支持的角色类型
- `owner`: 所有者
- `admin`: 管理员
- `editor`: 编辑者
- `normal`: 普通用户
- `dataset_operator`: 数据集操作员

### 请求示例

```bash
curl -X POST http://localhost:5001/remote-api/workspace/move-account \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "550e8400-e29b-41d4-a716-446655440000",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
    "role": "editor"
  }'
```

### 响应格式

#### 成功响应 (200)
```json
{
  "message": "账户成功移动到租户",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
  "role": "editor"
}
```

#### 账户已在租户中 (200)
```json
{
  "message": "账户已经在该租户下",
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440001",
  "role": "normal"
}
```

#### 错误响应

**400 Bad Request - 缺少参数**
```json
{
  "message": "缺少account_id参数"
}
```

**400 Bad Request - 无效角色**
```json
{
  "message": "无效的角色: invalid_role。有效角色包括: owner, admin, editor, normal, dataset_operator"
}
```

**404 Not Found - 账户不存在**
```json
{
  "message": "账户不存在"
}
```

**404 Not Found - 租户不存在**
```json
{
  "message": "租户不存在"
}
```

**400 Bad Request - 操作失败**
```json
{
  "message": "移动账户失败: 具体错误信息"
}
```

### 功能说明

1. **参数验证**: 接口会验证所有必需参数是否提供，以及角色是否有效
2. **存在性检查**: 验证账户和租户是否存在于数据库中
3. **重复检查**: 如果账户已经在目标租户中，会返回当前状态而不是错误
4. **事务处理**: 使用数据库事务确保操作的原子性
5. **自动切换**: 成功添加到租户后，会自动将该租户设为用户的当前租户

### 注意事项

1. 如果账户已经在目标租户中，接口会返回成功状态和当前角色信息
2. 移动账户到租户后，该租户会自动成为用户的当前活跃租户
3. 角色参数不区分大小写，但必须是预定义的有效角色之一
4. 操作失败时会自动回滚数据库事务

### 测试

可以使用提供的测试脚本进行API测试：

```bash
python test_workspace_api.py
```

该脚本包含正常情况和异常情况的测试用例。