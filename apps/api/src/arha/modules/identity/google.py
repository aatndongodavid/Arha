"""Google sign-in (F-AUT-01) with Authlib. Disabled when GOOGLE_OAUTH_CLIENT_ID is not set."""

from __future__ import annotations

from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi.responses import RedirectResponse

from arha.core import ratelimit
from arha.core.context import Ctx
from arha.core.errors import AppError, NotFound
from arha.core.ratelimit import valkey
from arha.core.security import new_token
from arha.modules.identity import service
from arha.modules.identity.models import User
from arha.settings import get_settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _client() -> AsyncOAuth2Client:
    st = get_settings()
    if not st.google_oauth_client_id or not st.google_oauth_client_secret:
        raise NotFound("google_disabled")
    return AsyncOAuth2Client(client_id=st.google_oauth_client_id,
                             client_secret=st.google_oauth_client_secret.get_secret_value(),
                             scope="openid email profile",
                             redirect_uri=f"{st.arha_api_url}/v1/auth/google/callback")


async def start(ctx: Ctx) -> RedirectResponse:
    client = _client()
    state = new_token(16)
    await valkey().set(f"oauth:{state}", "1", ex=600)
    url, _ = client.create_authorization_url(AUTHORIZE_URL, state=state)
    return RedirectResponse(url, status_code=303)


async def finish(ctx: Ctx, code: str, state: str) -> User:
    await ratelimit.limit("login", ctx.ip_hash or "")
    if not await valkey().getdel(f"oauth:{state}"):
        raise AppError("oauth_state_invalid", 400)
    client = _client()
    await client.fetch_token(TOKEN_URL, code=code)
    info = (await client.get(USERINFO_URL)).json()
    if not info.get("email_verified"):
        raise AppError("oauth_email_unverified", 400)
    user = await service.find_by_email(ctx.db, info["email"])
    if user is None:
        user = await service.create_user(ctx.db, email=info["email"], password=None, locale="fr",
                                         display_name=info.get("name"), google_sub=info["sub"], verified=True)
    elif user.google_sub is None:
        user.google_sub = info["sub"]
    return user
