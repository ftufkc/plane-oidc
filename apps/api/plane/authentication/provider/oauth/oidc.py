# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only

import base64
import hashlib
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urljoin, urlsplit

import jwt
import requests
from django.utils import timezone

from plane.authentication.adapter.oauth import OauthAdapter
from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.license.utils.instance_value import get_configuration_value


class OIDCOAuthProvider(OauthAdapter):
    provider = "oidc"
    scope = "openid email profile"

    def __init__(self, request, code=None, state=None, callback=None):
        enabled, client_id, client_secret, discovery_url = get_configuration_value(
            [
                {"key": "IS_OIDC_ENABLED", "default": os.environ.get("IS_OIDC_ENABLED", "0")},
                {"key": "OIDC_CLIENT_ID", "default": os.environ.get("OIDC_CLIENT_ID")},
                {"key": "OIDC_CLIENT_SECRET", "default": os.environ.get("OIDC_CLIENT_SECRET")},
                {"key": "OIDC_DISCOVERY_URL", "default": os.environ.get("OIDC_DISCOVERY_URL")},
            ]
        )
        if enabled != "1" or not all((client_id, client_secret, discovery_url)):
            self.fail("OIDC_NOT_CONFIGURED")
        try:
            response = requests.get(discovery_url, timeout=10)
            response.raise_for_status()
            self.discovery = response.json()
            for key in ("issuer", "authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri"):
                url = urlsplit(self.discovery[key])
                if url.scheme not in {"http", "https"} or not url.netloc or url.username:
                    raise ValueError("Invalid OIDC discovery URL")
        except (requests.RequestException, KeyError, ValueError):
            self.fail("OIDC_NOT_CONFIGURED")

        is_space = request.path.startswith("/auth/spaces/")
        callback_path = "/auth/spaces/oidc/callback/" if is_space else "/auth/oidc/callback/"
        redirect_uri = urljoin(base_host(request=request, is_space=is_space, is_app=not is_space), callback_path)
        params = {
            "client_id": client_id,
            "scope": self.scope,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
        if code is None:
            verifier = secrets.token_urlsafe(48)
            nonce = secrets.token_urlsafe(32)
            request.session["oidc_code_verifier"] = verifier
            request.session["oidc_nonce"] = nonce
            params.update(
                nonce=nonce,
                code_challenge_method="S256",
                code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode(),
            )
        auth_url = self.discovery["authorization_endpoint"] + "?" + urlencode(params)
        self.claims = None
        super().__init__(
            request,
            self.provider,
            client_id,
            self.scope,
            redirect_uri,
            auth_url,
            self.discovery["token_endpoint"],
            self.discovery["userinfo_endpoint"],
            client_secret,
            code,
            callback=callback,
        )

    @staticmethod
    def fail(key="OIDC_OAUTH_PROVIDER_ERROR"):
        raise AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[key], error_message=key)

    def set_token_data(self):
        verifier = self.request.session.pop("oidc_code_verifier", None)
        nonce = self.request.session.pop("oidc_nonce", None)
        if not verifier or not nonce:
            self.fail()
        try:
            response = requests.post(
                self.token_url,
                data={
                    "code": self.code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            token = response.json()
            key = jwt.PyJWKClient(self.discovery["jwks_uri"], timeout=10).get_signing_key_from_jwt(token["id_token"])
            self.claims = jwt.decode(
                token["id_token"],
                key.key,
                algorithms=["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
                audience=self.client_id,
                issuer=self.discovery["issuer"],
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            if self.claims.get("nonce") != nonce or self.claims.get("azp", self.client_id) != self.client_id:
                self.fail()
            if not token.get("access_token"):
                self.fail()
            expires = int(token.get("expires_in") or 0)
        except (requests.RequestException, jwt.PyJWTError, KeyError, ValueError, TypeError):
            self.fail()
        super().set_token_data(
            {
                "access_token": token["access_token"],
                "refresh_token": token.get("refresh_token"),
                "access_token_expired_at": timezone.now() + timedelta(seconds=expires) if expires else None,
                "refresh_token_expired_at": None,
                "id_token": token["id_token"],
            }
        )

    def set_user_data(self):
        try:
            response = requests.get(
                self.userinfo_url, headers={"Authorization": "Bearer " + self.token_data["access_token"]}, timeout=10
            )
            response.raise_for_status()
            info = response.json()
        except (requests.RequestException, ValueError):
            self.fail()
        if not info.get("sub") or info["sub"] != self.claims["sub"] or not info.get("email"):
            self.fail()
        if info.get("email_verified") is not True:
            self.fail("OAUTH_PROVIDER_UNVERIFIED_EMAIL")
        first_name = info.get("given_name", "")
        last_name = info.get("family_name", "")
        if not first_name:
            parts = info.get("name", "").split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""
        super().set_user_data(
            {
                "email": info["email"],
                "user": {
                    "provider_id": info["sub"],
                    "email": info["email"],
                    "avatar": info.get("picture", ""),
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_password_autoset": True,
                },
            }
        )
