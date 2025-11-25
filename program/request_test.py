#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
示例：
1）发 JSON（web_submit 等）：
   python oidc_request.py --url https://mgsdb.sjtu.edu.cn/api/development_data/web_submit --json payload.json

2）发表单（part_upload 等）：
   python oidc_request.py --url https://mgsdb.sjtu.edu.cn/api/development_data/part_upload --form op=init filename=example.zip content_type=application/zip object_prefix=devdata
"""

import argparse
import json
import requests

# ======= Keycloak 固定参数（根据你的配置已填好）=======
KEYCLOAK_BASE = "https://mgsdb.sjtu.edu.cn/keycloak/auth"
REALM = "unikorn"
CLIENT_ID = "unikorn"
CLIENT_SECRET = "f0701695-b9a9-43f6-ade4-00852036c149"  # 来自你的配置

# 可选：额外 header（有些后端需要）
EXTRA_HEADERS = {
    # "unicorn_user": "tester",
}

def get_access_token() -> str:
    """
    用 client_credentials 从 Keycloak 拿 access_token。
    兼容两种常见 token 端点路径（有的环境不带 /keycloak/auth）。
    """
    candidates = [
        f"{KEYCLOAK_BASE}/realms/{REALM}/protocol/openid-connect/token",
        f"https://mgsdb.sjtu.edu.cn/realms/{REALM}/protocol/openid-connect/token",
    ]
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        # 如网关/客户端要求，可加 scope：
        # "scope": "openid"
    }

    last_status = None
    last_body = None
    for url in candidates:
        try:
            resp = requests.post(url, data=data, timeout=20)
            if resp.status_code == 200:
                j = resp.json()
                return j["access_token"]
            else:
                last_status = resp.status_code
                try:
                    last_body = resp.json()
                except Exception:
                    last_body = resp.text
                print(f"[DEBUG] token {url} -> {last_status} {str(last_body)[:300]}")
        except Exception as e:
            print(f"[DEBUG] token {url} exception: {e}")
            last_status = "EXC"
            last_body = str(e)
    raise RuntimeError(f"获取 token 失败：{last_status} {last_body}")

def send_request(url: str, method: str, token: str, json_obj=None, form_kv=None, extra_headers=None):
    headers = {
        "Authorization": f"Bearer {token}",
    }
    if extra_headers:
        headers.update(extra_headers)

    if json_obj is not None:
        headers["Content-Type"] = "application/json"
        resp = requests.request(method.upper(), url, headers=headers, json=json_obj, timeout=180)
    elif form_kv is not None:
        resp = requests.request(method.upper(), url, headers=headers, data=form_kv, timeout=180)
    else:
        headers["Content-Type"] = "application/json"
        resp = requests.request(method.upper(), url, headers=headers, json={}, timeout=180)

    return resp

def parse_kv_list(kv_list):
    """把 ["a=1","b=2"] 解析成 dict"""
    out = {}
    for item in kv_list or []:
        if "=" not in item:
            raise ValueError(f"表单项必须 key=value，收到：{item}")
        k, v = item.split("=", 1)
        out[k] = v
    return out

def main():
    ap = argparse.ArgumentParser(description="Keycloak 认证后请求指定 URL（支持 JSON 或表单）")
    ap.add_argument("--url", required=True, help="目标接口 URL")
    ap.add_argument("--method", default="POST", help="HTTP 方法，默认 POST")
    ap.add_argument("--json", dest="json_path", help="JSON 文件路径（作为请求体）")
    ap.add_argument("--form", nargs="*", help="key=value 表单项（如 op=init filename=a.zip ...）")
    args = ap.parse_args()

    json_obj = None
    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            json_obj = json.load(f)

    form_kv = parse_kv_list(args.form) if args.form else None

    token = get_access_token()
    resp = send_request(args.url, args.method, token, json_obj=json_obj, form_kv=form_kv, extra_headers=EXTRA_HEADERS)

    print("Status:", resp.status_code)
    try:
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(resp.text)

if __name__ == "__main__":
    main()
