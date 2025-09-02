from typing import Any, Optional

from flask import request
from flask_restful import Resource  # type: ignore
from werkzeug.exceptions import BadRequest, NotFound

from controllers.remote_api import api
from models.account import Account, Tenant, TenantAccountJoin, TenantAccountRole
from models.engine import db
from services.account_service import TenantService


class RemoteMoveAccountToTenantApi(Resource):
    def post(self) -> tuple[dict[str, Any], int]:
        """将账户移动到指定租户下"""
        # 获取请求参数
        json_data: Optional[dict[str, Any]] = request.json
        if not json_data:
            raise BadRequest("请求体必须是JSON格式")

        account_id = json_data.get("account_id")
        tenant_id = json_data.get("tenant_id")
        role = json_data.get("role", "normal")  # 默认角色为normal

        if not account_id:
            raise BadRequest("缺少account_id参数")

        if not tenant_id:
            raise BadRequest("缺少tenant_id参数")

        # 验证角色是否有效
        if not TenantAccountRole.is_valid_role(role):
            raise BadRequest(f"无效的角色: {role}。有效角色包括: owner, admin, editor, normal, dataset_operator")

        # 验证账户是否存在
        account = db.session.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise NotFound("账户不存在")

        # 验证租户是否存在
        tenant = db.session.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise NotFound("租户不存在")

        # 检查账户是否已经在该租户下
        existing_join = (
            db.session.query(TenantAccountJoin).filter_by(tenant_id=tenant_id, account_id=account_id).first()
        )

        if existing_join:
            return {
                "message": "账户已经在该租户下",
                "account_id": account_id,
                "tenant_id": tenant_id,
                "role": existing_join.role,
            }, 200

        try:
            # 创建租户成员关系
            TenantService.create_tenant_member(tenant, account, role)

            # 切换账户的当前租户
            TenantService.switch_tenant(account, tenant_id)

            return {
                "message": "账户成功移动到租户",
                "account_id": account_id,
                "tenant_id": tenant_id,
                "role": role,
            }, 200

        except Exception as e:
            db.session.rollback()
            raise BadRequest(f"移动Account失败: {str(e)}")


# 注册API路由
api.add_resource(RemoteMoveAccountToTenantApi, "/workspace/move-account")
