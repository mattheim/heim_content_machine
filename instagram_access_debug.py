from __future__ import annotations

import argparse
import os
from typing import Any

import requests


DEFAULT_GRAPH_URL = "https://graph.facebook.com/v23.0"
REQUIRED_INSIGHTS_PERMISSIONS = (
    "instagram_basic",
    "instagram_manage_insights",
    "pages_read_engagement",
    "pages_show_list",
)
INSTAGRAM_LOGIN_INSIGHTS_PERMISSIONS = (
    "instagram_business_basic",
    "instagram_business_manage_insights",
)


def _graph_get(graph_url: str, path: str, access_token: str, params: dict[str, Any] | None = None) -> dict:
    query = dict(params or {})
    query["access_token"] = access_token
    url = f"{graph_url.rstrip('/')}/{path.lstrip('/')}"
    try:
        response = requests.get(url, params=query, timeout=30)
    except requests.RequestException:
        return {"error": {"message": f"Request failed before Meta responded. Check DNS/network access for {graph_url}."}}
    try:
        payload = response.json()
    except ValueError:
        return {"error": {"message": f"Non-JSON response with status {response.status_code}"}}
    return payload


def _granted_permissions(payload: dict) -> set[str]:
    granted = set()
    for item in payload.get("data", []):
        if item.get("status") == "granted" and item.get("permission"):
            granted.add(item["permission"])
    return granted


def print_permission_status(graph_url: str, access_token: str) -> None:
    me = _graph_get(graph_url, "/me", access_token, {"fields": "id,name,username"})
    print("Token identity check")
    if "error" in me:
        print(f"/me failed: {me['error'].get('message')}")
    else:
        identity = ", ".join(f"{key}={value}" for key, value in me.items() if key != "id") or "no display fields"
        print(f"id={me.get('id')} {identity}")

    permissions = _graph_get(graph_url, "/me/permissions", access_token)
    if "error" in permissions:
        print(f"\nToken permission check unavailable: {permissions['error'].get('message')}")
        print("This usually means the token is not a Facebook Login user token.")
        print("If this is an Instagram Login token, use the Instagram Business permissions:")
        for permission in INSTAGRAM_LOGIN_INSIGHTS_PERMISSIONS:
            print(f"{permission}: check in Meta token generator")
    else:
        granted = _granted_permissions(permissions)
        print("\nToken permission check")
        for permission in REQUIRED_INSIGHTS_PERMISSIONS:
            status = "granted" if permission in granted else "missing"
            print(f"{permission}: {status}")

    accounts = _graph_get(
        graph_url,
        "/me/accounts",
        access_token,
        {"fields": "id,name,instagram_business_account{id,username}"},
    )
    if "error" in accounts:
        print(f"\nPage/Instagram account check failed: {accounts['error'].get('message')}")
        return

    print("\nConnected pages")
    rows = accounts.get("data", [])
    if not rows:
        print("No Facebook Pages returned for this token.")
        return
    for page in rows:
        ig_account = page.get("instagram_business_account") or {}
        ig_label = ig_account.get("username") or ig_account.get("id") or "no linked Instagram account returned"
        print(f"{page.get('name')} page_id={page.get('id')} instagram={ig_label}")


def main() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Check whether the configured Instagram token can read insights.")
    parser.add_argument("--graph-url", default=os.getenv("GRAPH_URL", DEFAULT_GRAPH_URL), help="Instagram Graph API base URL.")
    args = parser.parse_args()

    token = os.getenv("ACCESS_TOKEN") or os.getenv("IG_ACCESS_TOKEN")
    if not token:
        print("Missing token. Set ACCESS_TOKEN or IG_ACCESS_TOKEN in .env.")
        return

    print_permission_status(args.graph_url, token)


if __name__ == "__main__":
    main()
