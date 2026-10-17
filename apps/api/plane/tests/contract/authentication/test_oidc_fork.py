from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.provider.oauth.oidc import OIDCOAuthProvider
from plane.authentication.views.app.oidc import OIDCCallbackEndpoint
from plane.db.models import User, Workspace, WorkspaceMember
from plane.license.api.views.instance import InstanceUsersEndpoint
from plane.license.models import Instance, InstanceAdmin


@pytest.fixture
def discovery():
    return {
        "issuer": "https://idp.example/realm",
        "authorization_endpoint": "https://idp.example/auth",
        "token_endpoint": "https://idp.example/token",
        "userinfo_endpoint": "https://idp.example/userinfo",
        "jwks_uri": "https://idp.example/certs",
    }


@pytest.mark.parametrize(
    "path,callback", [("/auth/oidc/", "/auth/oidc/callback/"), ("/auth/spaces/oidc/", "/auth/spaces/oidc/callback/")]
)
@override_settings(WEB_URL="http://plane.example:3307", APP_BASE_URL="", SPACE_BASE_URL="")
def test_oidc_public_redirect_and_pkce(discovery, path, callback):
    request = RequestFactory().get(path, HTTP_HOST="api:8000")
    request.session = {}
    with (
        patch(
            "plane.authentication.provider.oauth.oidc.get_configuration_value",
            return_value=("1", "client", "secret", "https://idp.example/discovery"),
        ),
        patch("plane.authentication.provider.oauth.oidc.requests.get") as get,
    ):
        get.return_value.json.return_value = discovery
        provider = OIDCOAuthProvider(request, state="test-state")
    assert provider.redirect_uri == "http://plane.example:3307" + callback
    assert "code_challenge_method=S256" in provider.auth_url
    assert request.session["oidc_nonce"] in provider.auth_url
    assert request.session["oidc_code_verifier"] not in provider.auth_url
    get.assert_called_once_with("https://idp.example/discovery", timeout=10)


@pytest.mark.parametrize("state,stored", [(None, None), ("wrong", "expected"), ("", "")])
@override_settings(WEB_URL="http://plane.example:3307", APP_BASE_URL="")
def test_callback_rejects_missing_mismatched_state(state, stored):
    request = RequestFactory().get(
        "/auth/oidc/callback/", {"code": "code", **({"state": state} if state is not None else {})}
    )
    request.session = {"oidc_state": stored}
    with patch("plane.authentication.views.app.oidc.OIDCOAuthProvider") as provider:
        response = OIDCCallbackEndpoint.as_view()(request)
    provider.assert_not_called()
    assert response.url.startswith("http://plane.example:3307")
    assert "oidc_state" not in request.session


def test_oidc_disabled_does_not_contact_provider():
    with (
        patch(
            "plane.authentication.provider.oauth.oidc.get_configuration_value",
            return_value=("0", "client", "secret", "url"),
        ),
        patch("plane.authentication.provider.oauth.oidc.requests.get") as get,
    ):
        with pytest.raises(AuthenticationException):
            OIDCOAuthProvider(SimpleNamespace())
        get.assert_not_called()


@pytest.mark.parametrize(
    "info",
    [
        {"sub": "other", "email": "x@example.com", "email_verified": True},
        {"sub": "subject", "email": "x@example.com", "email_verified": False},
        {"sub": "subject", "email": "x@example.com"},
    ],
)
def test_oidc_rejects_unverified_or_mismatched_identity(info):
    provider = OIDCOAuthProvider.__new__(OIDCOAuthProvider)
    provider.userinfo_url = "https://idp.example/userinfo"
    provider.token_data = {"access_token": "token"}
    provider.claims = {"sub": "subject"}
    with patch("plane.authentication.provider.oauth.oidc.requests.get") as get:
        get.return_value.json.return_value = info
        with pytest.raises(AuthenticationException):
            provider.set_user_data()


@pytest.fixture
def admin_user(db):
    user = User.objects.create(email="admin@example.com", username="admin", first_name="Admin")
    instance = Instance.objects.create(
        instance_name="Test", instance_id="test", current_version="1.4.2", last_checked_at=timezone.now()
    )
    InstanceAdmin.objects.create(instance=instance, user=user, role=20)
    return user


def invoke(method, user, data=None, pk=None):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/api/instances/users/", data=data or {}, format="json")
    if user:
        force_authenticate(request, user=user)
    return InstanceUsersEndpoint.as_view()(request, **({"pk": pk} if pk else {}))


@pytest.mark.django_db
def test_member_management_create_deactivate_and_delete(admin_user):
    response = invoke(
        "post", admin_user, {"email": "New@Example.com", "first_name": "New", "password": "Safe-Test!Password-83761"}
    )
    assert response.status_code == 201, response.data
    user = User.objects.get(pk=response.data["id"])
    assert user.email == "new@example.com"
    assert user.check_password("Safe-Test!Password-83761")
    assert invoke("patch", admin_user, {"is_active": False}, user.pk).status_code == 200
    user.refresh_from_db()
    assert user.is_active is False
    assert invoke("delete", admin_user, pk=user.pk).status_code == 204
    assert not User.objects.filter(pk=user.pk).exists()


@pytest.mark.django_db
def test_member_management_rejects_non_admin_and_admin_lockout(admin_user):
    user = User.objects.create(email="other@example.com", username="other")
    assert invoke("get", None).status_code in {401, 403}
    assert invoke("get", user).status_code == 403
    assert invoke("patch", admin_user, {"is_active": False}, admin_user.pk).status_code == 403
    assert invoke("delete", admin_user, pk=admin_user.pk).status_code == 403
    assert invoke("patch", admin_user, {"is_active": "false"}, user.pk).status_code == 400


@pytest.mark.django_db
def test_member_management_validates_email_password_and_duplicate(admin_user):
    assert invoke("post", admin_user, {"email": "not-email", "first_name": "X", "password": "weak"}).status_code == 400
    assert (
        invoke(
            "post",
            admin_user,
            {"email": "admin@example.com", "first_name": "X", "password": "Safe-Test!Password-83761"},
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_default_workspaces_and_role(admin_user):
    workspace = Workspace.objects.create(name="Team", slug="team", owner=admin_user)
    user = User.objects.create(email="oidc@example.com", username="oidc")
    adapter = Adapter(SimpleNamespace(), "oidc")
    with patch("plane.license.utils.instance_value.get_configuration_value", side_effect=[("team,missing",), ("15",)]):
        adapter._Adapter__auto_join_default_workspace(user)
    assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 15


@pytest.mark.parametrize("nonce,expires,accepted", [("nonce", 60, True), ("wrong", 60, False), ("nonce", -60, False)])
def test_id_token_signature_claims_nonce_and_expiry(discovery, nonce, expires, accepted):
    import time
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = int(time.time())
    claims = {
        "sub": "subject",
        "iss": discovery["issuer"],
        "aud": "client",
        "iat": now,
        "exp": now + expires,
        "nonce": nonce,
    }
    token = jwt.encode(claims, key, algorithm="RS256")
    provider = OIDCOAuthProvider.__new__(OIDCOAuthProvider)
    provider.request = SimpleNamespace(session={"oidc_nonce": "nonce", "oidc_code_verifier": "verifier"})
    provider.client_id = "client"
    provider.client_secret = "secret"
    provider.code = "authorization-code"
    provider.redirect_uri = "http://plane.example:3307/auth/oidc/callback/"
    provider.token_url = discovery["token_endpoint"]
    provider.discovery = discovery
    with (
        patch("plane.authentication.provider.oauth.oidc.requests.post") as post,
        patch("plane.authentication.provider.oauth.oidc.jwt.PyJWKClient") as jwks,
    ):
        post.return_value.json.return_value = {"id_token": token, "access_token": "access", "expires_in": 60}
        jwks.return_value.get_signing_key_from_jwt.return_value.key = key.public_key()
        if accepted:
            provider.set_token_data()
            assert provider.token_data["access_token"] == "access"
        else:
            with pytest.raises(AuthenticationException):
                provider.set_token_data()
        assert "oidc_nonce" not in provider.request.session
