import logging
from datetime import UTC, datetime
from typing import Optional

import requests
from flask import current_app, redirect, request
from flask_restful import Resource  # type: ignore
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import Unauthorized

from configs import dify_config
from constants.languages import languages
from events.tenant_event import tenant_was_created
from extensions.ext_database import db
from libs.helper import extract_remote_ip
from libs.oauth import GitHubOAuth, GoogleOAuth, OAuthUserInfo, CustomOAuth
from models import Account, Tenant
from models.account import AccountStatus
from services.account_service import AccountService, RegisterService, TenantService, _get_userinfo_from_token
from services.errors.account import AccountNotFoundError, AccountRegisterError
from services.errors.workspace import WorkSpaceNotAllowedCreateError, WorkSpaceNotFoundError
from services.feature_service import FeatureService

from .. import api


def get_oauth_providers():
    with current_app.app_context():
        if not dify_config.GITHUB_CLIENT_ID or not dify_config.GITHUB_CLIENT_SECRET:
            github_oauth = None
        else:
            github_oauth = GitHubOAuth(
                client_id=dify_config.GITHUB_CLIENT_ID,
                client_secret=dify_config.GITHUB_CLIENT_SECRET,
                redirect_uri=dify_config.CONSOLE_API_URL + "/console/api/oauth/authorize/github",
            )
        if not dify_config.GOOGLE_CLIENT_ID or not dify_config.GOOGLE_CLIENT_SECRET:
            google_oauth = None
        else:
            google_oauth = GoogleOAuth(
                client_id=dify_config.GOOGLE_CLIENT_ID,
                client_secret=dify_config.GOOGLE_CLIENT_SECRET,
                redirect_uri=dify_config.CONSOLE_API_URL + "/console/api/oauth/authorize/google",
            )
        dify_config.CUSTOM_CLIENT_ID = "dify"
        dify_config.CUSTOM_CLIENT_SECRET = "dify"
        logging.info("dify_config.CUSTOM_CLIENT_ID: %s", dify_config.CUSTOM_CLIENT_ID)
        logging.info("dify_config.CUSTOM_CLIENT_SECRET: %s", dify_config.CUSTOM_CLIENT_SECRET)
        if not dify_config.CUSTOM_CLIENT_ID or not dify_config.CUSTOM_CLIENT_SECRET:
            logging.info("get_oauth_providers not id or secret")
            custom_oauth = None
        else:
            logging.info("get_oauth_providers id or secret")
            custom_oauth = CustomOAuth(
                client_id=dify_config.CUSTOM_CLIENT_ID,
                client_secret=dify_config.CUSTOM_CLIENT_SECRET,
                redirect_uri=dify_config.CONSOLE_API_URL + "/console/api/oauth/authorize/custom",
            )
            logging.info("dify_config.CONSOLE_API_URL: %s", dify_config.CONSOLE_API_URL)
        OAUTH_PROVIDERS = {"github": github_oauth, "google": google_oauth, "custom": custom_oauth}
        return OAUTH_PROVIDERS


class OAuthLogin(Resource):
    def get(self, provider: str):
        logging.info("OAuthLogin get provider: %s",provider)
        invite_token = request.args.get("invite_token") or None
        OAUTH_PROVIDERS = get_oauth_providers()
        with current_app.app_context():
            oauth_provider = OAUTH_PROVIDERS.get(provider)
        if not oauth_provider:
            return {"error": "Invalid provider"}, 400

        auth_url = oauth_provider.get_authorization_url(invite_token=invite_token)
        logging.info("OAuthLogin auth_url: %s", auth_url)
        return redirect(auth_url)


class OAuthCallback(Resource):

    def get(self, provider: str):
        logging.info("OAuthCallback get provider: %s",provider)
        OAUTH_PROVIDERS = get_oauth_providers()
        with current_app.app_context():
            oauth_provider = OAUTH_PROVIDERS.get(provider)
        if not oauth_provider:
            return {"error": "Invalid provider"}, 400

        code = request.args.get("code")
        logging.info("OAuthCallback code: %s", code)
        state = request.args.get("state")
        invite_token = None
        if state:
            invite_token = state

        try:
            token = oauth_provider.get_access_token(code)
            logging.info("OAuthCallback token: %s", token)
            dept, user_name, email, id = _get_userinfo_from_token(token)
            logging.info("OAuthCallback dept: %s", dept)
            user_info = oauth_provider.get_user_info(token)
            logging.info("OAuthCallback user_info: %s", user_info)

            if user_info.name and user_info.name.startswith("wb"):
                return {"error": "Permission denied"}, 400
        except requests.exceptions.RequestException as e:
            error_text = e.response.text if e.response else str(e)
            logging.exception(f"An error occurred during the OAuth process with {provider}: {error_text}")
            return {"error": "OAuth process failed"}, 400

        account = db.session.query(Account).filter(Account.email == user_info.email).first()
        if not account:
            logging.info("OAuthCallback not account")
            account = RegisterService.register(
                email=user_info.email, name=user_info.name, language="zh-Hans", status=AccountStatus.PENDING, is_setup=True
            )
            tenant_name = dept + "'s Workspace"
            tenant = db.session.query(Tenant).filter(Tenant.name == tenant_name).first()
            TenantService.create_tenant_member(tenant, account, "admin")
            TenantService.switch_tenant(account, tenant.id)

        if account.status == AccountStatus.PENDING.value:
            account.status = AccountStatus.ACTIVE.value
            account.initialized_at = datetime.now(UTC).replace(tzinfo=None)
            db.session.commit()

        try:
            TenantService.create_owner_tenant_if_not_exist(account)
        except Unauthorized:
            return redirect(f"{dify_config.CONSOLE_WEB_URL}/signin?message=Workspace not found.")
        except WorkSpaceNotAllowedCreateError:
            return redirect(
                f"{dify_config.CONSOLE_WEB_URL}/signin"
                "?message=Workspace not found, please contact system admin to invite you to join in a workspace."
            )

        token_pair = AccountService.login(
            account=account,
            ip_address=extract_remote_ip(request),
        )

        return redirect(
            f"{dify_config.CONSOLE_WEB_URL}?access_token={token_pair.access_token}&refresh_token={token_pair.refresh_token}"
        )


def _get_account_by_openid_or_email(provider: str, user_info: OAuthUserInfo) -> Optional[Account]:
    account: Optional[Account] = Account.get_by_openid(provider, user_info.id)

    if not account:
        with Session(db.engine) as session:
            account = session.execute(select(Account).filter_by(email=user_info.email)).scalar_one_or_none()

    return account


def _generate_account(provider: str, user_info: OAuthUserInfo):
    # Get account by openid or email.
    account = _get_account_by_openid_or_email(provider, user_info)

    if account:
        tenant = TenantService.get_join_tenants(account)
        if not tenant:
            if not FeatureService.get_system_features().is_allow_create_workspace:
                raise WorkSpaceNotAllowedCreateError()
            else:
                tenant = TenantService.create_tenant(f"{account.name}'s Workspace")
                TenantService.create_tenant_member(tenant, account, role="owner")
                account.current_tenant = tenant
                tenant_was_created.send(tenant)

    if not account:
        if not FeatureService.get_system_features().is_allow_register:
            raise AccountNotFoundError()
        account_name = user_info.name or "Dify"
        account = RegisterService.register(
            email=user_info.email, name=account_name, password=None, open_id=user_info.id, provider=provider
        )

        # Set interface language
        preferred_lang = request.accept_languages.best_match(languages)
        if preferred_lang and preferred_lang in languages:
            interface_language = preferred_lang
        else:
            interface_language = languages[0]
        account.interface_language = interface_language
        db.session.commit()

    # Link account
    AccountService.link_account_integrate(provider, user_info.id, account)

    return account


api.add_resource(OAuthLogin, "/oauth/login/<provider>")
api.add_resource(OAuthCallback, "/oauth/authorize/<provider>")
