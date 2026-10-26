import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt


class OIDCError(Exception):
    pass


class OIDCClient:
    def __init__(
        self, issuer: str, client_id: str, client_secret: str, redirect_uri: str, scopes: str
    ):
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self._configuration: tuple[float, dict] | None = None
        self._jwks: tuple[float, dict] | None = None

    async def configuration(self) -> dict:
        if self._configuration and self._configuration[0] > time.monotonic():
            return self._configuration[1]
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{self.issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            data = response.json()
        if data.get("issuer", "").rstrip("/") != self.issuer:
            raise OIDCError("OIDC discovery issuer mismatch")
        self._configuration = (time.monotonic() + 300, data)
        return data

    async def authorization_url(self) -> tuple[str, dict[str, str]]:
        config = await self.configuration()
        state = secrets.token_urlsafe(32)
        binding = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "max_age": "0",
        }
        return f"{config['authorization_endpoint']}?{urlencode(params)}", {
            "state": state,
            "binding": binding,
            "nonce": nonce,
            "verifier": verifier,
        }

    async def exchange(self, code: str, verifier: str, nonce: str) -> dict:
        config = await self.configuration()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                config["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code_verifier": verifier,
                },
            )
            response.raise_for_status()
            token = response.json()
        id_token = token.get("id_token")
        if not isinstance(id_token, str):
            raise OIDCError("OIDC response did not include an ID token")
        claims = await self._decode_id_token(id_token)
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OIDCError("OIDC nonce mismatch")
        return claims

    async def _decode_id_token(self, token: str) -> dict:
        config = await self.configuration()
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")
        allowed = set(config.get("id_token_signing_alg_values_supported", [])) & {
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
        }
        if algorithm not in allowed:
            raise OIDCError("OIDC signing algorithm is not allowed")
        jwks = await self._get_jwks(config["jwks_uri"])
        key_data = next(
            (item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None
        )
        if key_data is None:
            self._jwks = None
            jwks = await self._get_jwks(config["jwks_uri"])
            key_data = next(
                (item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")),
                None,
            )
        if key_data is None:
            raise OIDCError("OIDC signing key was not found")
        key = jwt.PyJWK.from_dict(key_data).key
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=self.client_id,
            issuer=config["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )

    async def _get_jwks(self, url: str) -> dict:
        if self._jwks and self._jwks[0] > time.monotonic():
            return self._jwks[1]
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        self._jwks = (time.monotonic() + 300, data)
        return data


def has_role(claims: dict, claim_name: str, required_role: str) -> bool:
    value = claims.get(claim_name)
    if isinstance(value, str):
        return value == required_role
    if isinstance(value, dict):
        return required_role in value
    if isinstance(value, list):
        return any(
            item == required_role or (isinstance(item, dict) and required_role in item)
            for item in value
        )
    return False


def has_required_authentication(claims: dict, required_methods: set[str] | None = None) -> bool:
    amr = claims.get("amr", [])
    if isinstance(amr, str):
        amr = amr.split()
    methods = set(amr) if isinstance(amr, list) else set()
    required = required_methods or {"pwd", "mfa"}
    return required.issubset(methods)
