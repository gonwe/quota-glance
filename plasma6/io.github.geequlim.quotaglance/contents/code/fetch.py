#!/usr/bin/env python3
"""Collect the same quota sources used by the GNOME Quota Glance extension."""

import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path


HOME = Path.home()
PROVIDERS = {
    "codex": ("Codex", "读取已登录 Codex CLI 的额度限制"),
    "copilot": ("GitHub Copilot", "读取已登录 GitHub CLI 的高级请求额度"),
    "zai": ("Z.ai", "Coding Plan 额度周期"),
    "opencode-go": ("OpenCode Go", "工作区用量限制"),
    "deepseek": ("DeepSeek", "API 账户余额"),
}
ALLOWED_ENV = {
    "PATH",
    "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
    "NO_PROXY", "no_proxy",
    "DEEPSEEK_API_KEY",
    "Z_AI_API_KEY",
    "OPENCODE_GO_WORKSPACE_ID",
    "OPENCODE_GO_AUTH_COOKIE",
}
ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env_file(path: Path, target: dict) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return
    for source_line in lines:
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ASSIGNMENT.match(line)
        if not match or match.group(1) not in ALLOWED_ENV:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        target[match.group(1)] = value


def load_environment() -> dict:
    env = {key: value for key, value in os.environ.items() if key in ALLOWED_ENV}
    parse_env_file(Path("/etc/environment"), env)
    env_dir = HOME / ".config/environment.d"
    if env_dir.is_dir():
        for path in sorted(env_dir.glob("*.conf")):
            parse_env_file(path, env)
    parse_env_file(HOME / ".config/quota-glance/env", env)
    for upper, lower in (("HTTP_PROXY", "http_proxy"), ("HTTPS_PROXY", "https_proxy"), ("NO_PROXY", "no_proxy")):
        value = env.get(upper) or env.get(lower)
        if value:
            env[upper] = value
            env[lower] = value
    return env


def record(value) -> dict:
    return value if isinstance(value, dict) else {}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def epoch_ms(value):
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    result = number(value)
    if result is None:
        return None
    return int(result * 1000 if result < 10_000_000_000 else result)


def metric(label, value, remaining=None, detail="", reset_at=None):
    percent = number(remaining)
    return {
        "label": label,
        "value": value,
        "progress": None if percent is None else max(0.0, min(1.0, percent / 100.0)),
        "detail": detail,
        "resetAt": epoch_ms(reset_at),
    }


def provider_result(provider_id, ok=False, error="", subtitle="", badge="", metrics=None, details=None, panel_value=""):
    name, description = PROVIDERS[provider_id]
    return {
        "id": provider_id,
        "name": name,
        "description": description,
        "ok": ok,
        "error": error,
        "subtitle": subtitle,
        "badge": badge,
        "panelValue": panel_value,
        "metrics": metrics or [],
        "details": details or [],
    }


def read_rpc_response(process, request_id, timeout=18.0):
    if process.stdout is None:
        raise RuntimeError("Codex app-server stdout unavailable")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], max(0.0, deadline - time.monotonic()))
        if not ready:
            break
        raw = process.stdout.readline(1024 * 1024)
        if not raw:
            break
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        if message.get("id") != request_id:
            continue
        if "error" in message:
            raise RuntimeError("Codex app-server request failed")
        result = message.get("result")
        return result if isinstance(result, dict) else {}
    raise TimeoutError("Codex app-server did not reply")


def send_rpc(process, payload):
    if process.stdin is None:
        raise RuntimeError("Codex app-server stdin unavailable")
    process.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    process.stdin.flush()


def codex_window(value, fallback_label):
    value = record(value)
    used = number(value.get("usedPercent"))
    if used is None:
        return None
    remaining = max(0.0, min(100.0, 100.0 - used))
    duration = number(value.get("windowDurationMins"))
    if duration is None:
        duration = 300 if fallback_label == "5小时" else 10080
    reset_at = epoch_ms(value.get("resetsAt"))
    return metric(fallback_label, f"{remaining:.0f}%", remaining, "", reset_at), duration


def collect_codex(env):
    executable = shutil.which("codex", path=env.get("PATH")) or "/usr/bin/codex"
    if not Path(executable).is_file():
        return provider_result("codex", error="未找到 Codex CLI")
    child_env = os.environ.copy()
    child_env.update(env)
    try:
        process = subprocess.Popen(
            [executable, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=child_env, bufsize=0,
        )
    except OSError:
        return provider_result("codex", error="无法启动 Codex CLI")
    try:
        send_rpc(process, {
            "id": 1,
            "method": "initialize",
            "params": {"clientInfo": {"name": "quota-glance-plasma", "version": "1.1.0"}, "capabilities": {"experimentalApi": True}},
        })
        read_rpc_response(process, 1)
        send_rpc(process, {"method": "initialized"})
        send_rpc(process, {"id": 2, "method": "account/read", "params": {}})
        account_result = read_rpc_response(process, 2)
        send_rpc(process, {"id": 3, "method": "account/rateLimits/read", "params": None})
        rate_result = read_rpc_response(process, 3)
        buckets = record(rate_result.get("rateLimitsByLimitId"))
        limits = record(buckets.get("codex") or rate_result.get("rateLimits") or rate_result)
        account = record(record(account_result).get("account"))
        metrics = []
        for key, fallback in (("primary", "5小时"), ("secondary", "7天")):
            parsed = codex_window(limits.get(key), fallback)
            if parsed:
                metrics.append(parsed[0])
        if not metrics:
            return provider_result("codex", error="Codex 暂无额度数据")
        plan = str(limits.get("planType") or account.get("planType") or "").replace("_", " ").title()
        balance = record(limits.get("credits")).get("balance")
        details = []
        if balance is not None:
            details.append(f"点数：{balance}")
        credits = record(limits.get("credits"))
        if credits.get("unlimited") is True:
            details.append("点数无限")
        return provider_result(
            "codex", True, subtitle=str(account.get("email") or "Codex 账户"),
            badge=plan, metrics=metrics, details=details,
            panel_value=next((item["value"] for item in metrics if item["label"] == "7天"), metrics[0]["value"]),
        )
    except Exception:
        return provider_result("codex", error="Codex 数据暂不可用")
    finally:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass


def collect_copilot(env):
    executable = shutil.which("gh", path=env.get("PATH"))
    if not executable:
        return provider_result("copilot", error="请安装 GitHub CLI（gh）以使用 Copilot")
    argv = [
        executable, "api",
        "-H", "Accept: application/json",
        "-H", "Editor-Version: vscode/1.96.2",
        "-H", "X-Github-Api-Version: 2025-04-01",
        "/copilot_internal/user",
    ]
    child_env = os.environ.copy()
    child_env.update(env)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=18, env=child_env, check=True)
        payload = json.loads(completed.stdout)
    except FileNotFoundError:
        return provider_result("copilot", error="请先安装并登录 GitHub CLI（gh）")
    except subprocess.TimeoutExpired:
        return provider_result("copilot", error="GitHub Copilot 请求超时")
    except (OSError, subprocess.CalledProcessError, UnicodeError, json.JSONDecodeError):
        return provider_result("copilot", error="GitHub Copilot 数据暂不可用，请检查 gh 登录状态")
    snapshots = record(record(payload).get("quota_snapshots"))
    if not snapshots:
        return provider_result("copilot", error="GitHub Copilot 暂无额度数据")
    reset_fallback = record(payload).get("quota_reset_date_utc") or record(payload).get("quota_reset_date")
    names = {
        "premium_interactions": "高级请求",
        "chat": "对话",
        "completions": "代码补全",
    }
    metrics = []
    for quota_id, label in names.items():
        quota = record(snapshots.get(quota_id))
        if not quota:
            continue
        unlimited = quota.get("unlimited") is True
        remaining = number(quota.get("remaining"))
        entitlement = number(quota.get("entitlement"))
        percent = number(quota.get("percent_remaining"))
        if percent is None and remaining is not None and entitlement:
            percent = remaining / entitlement * 100
        reset = quota.get("timestamp_utc") or reset_fallback
        detail = "无限额度" if unlimited else ""
        if not unlimited and remaining is not None and entitlement is not None:
            detail = f"剩余 {remaining:,.0f} / {entitlement:,.0f}"
        value = "无限" if unlimited else ("--" if percent is None else f"{percent:.0f}%")
        metrics.append(metric(label, value, 100 if unlimited else percent, detail, reset))
    if not metrics:
        return provider_result("copilot", error="GitHub Copilot 返回了空额度")
    plan = str(record(payload).get("copilot_plan") or "").replace("_", " ").title()
    premium = next((item["value"] for item in metrics if item["label"] == "高级请求"), metrics[0]["value"])
    return provider_result("copilot", True, subtitle=str(record(payload).get("login") or ""), badge=plan, metrics=metrics, panel_value=premium)


def get_url(url, headers, env, timeout=12, max_bytes=2 * 1024 * 1024):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(max_bytes)


def format_plan(value):
    return " ".join(part.capitalize() for part in re.split(r"[_-]+", str(value or "").lower()) if part)


def zai_window_kind(limit, now_ms):
    kind = str(limit.get("type") or "").upper()
    unit = number(limit.get("unit"))
    count = number(limit.get("number"))
    if kind == "TOKENS_LIMIT" and unit == 3 and count == 5:
        return "5h"
    if kind == "TOKENS_LIMIT" and unit == 6 and count == 1:
        return "7d"
    if "WEEK" in kind or "7D" in kind:
        return "7d"
    if kind == "TOKENS_LIMIT":
        return "5h"
    reset = epoch_ms(limit.get("nextResetTime"))
    if reset:
        hours = (reset - now_ms) / 3_600_000
        if 0 < hours <= 12:
            return "5h"
        if hours >= 72:
            return "7d"
    return None


def collect_zai(env):
    api_key = env.get("Z_AI_API_KEY", "")
    if not api_key:
        return provider_result("zai", error="请设置 Z_AI_API_KEY 以启用 Z.ai")
    try:
        raw = get_url(
            "https://api.z.ai/api/monitor/usage/quota/limit",
            {"Accept": "application/json", "Authorization": api_key, "User-Agent": "Quota-Glance/Plasma-1.1.0"},
            env,
        )
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError):
        return provider_result("zai", error="Z.ai 额度暂不可用")
    data = record(record(payload).get("data"))
    limits = [record(item) for item in data.get("limits", []) if isinstance(item, dict)]
    if not limits:
        return provider_result("zai", error="Z.ai 暂无额度数据")
    selected = {}
    for limit in limits:
        kind = zai_window_kind(limit, int(time.time() * 1000))
        if kind and kind not in selected:
            selected[kind] = limit
    entries = list(selected.items()) if selected else [(f"limit-{i}", item) for i, item in enumerate(limits)]
    metrics = []
    for kind, limit in entries:
        raw_used = number(limit.get("percentage"))
        remaining = None if raw_used is None else max(0.0, min(100.0, 100.0 - round(raw_used)))
        label = {"5h": "5小时", "7d": "7天"}.get(kind, str(limit.get("type") or "额度").replace("_", " ").lower())
        current = number(limit.get("currentValue"))
        total = number(limit.get("number"))
        detail = ""
        if current is not None and total is not None:
            detail = f"已使用 {current:,.0f} / {total:,.0f}"
        metrics.append(metric(label, "--" if remaining is None else f"{remaining:.0f}%", remaining, detail, limit.get("nextResetTime")))
    success = record(payload).get("success") is not False
    if not success:
        return provider_result("zai", error=str(record(payload).get("msg") or "Z.ai 请求未成功"))
    summary = next((item["value"] for item in metrics if item["label"] == "7天"), metrics[0]["value"])
    return provider_result("zai", True, badge=format_plan(data.get("level")), metrics=metrics, panel_value=summary)


def build_opencode_cookie(value):
    trimmed = value.strip()
    if not trimmed:
        return ""
    return trimmed if "auth=" in trimmed or ";" in trimmed else f"auth={trimmed}"


def parse_opencode_window(html, field, now_ms):
    prefix = re.escape(field) + r":\$R\[\d+\]=\{([^}]*)\}"
    for match in re.finditer(prefix, html):
        body = match.group(1)
        usage_match = re.search(r"usagePercent:\s*(-?\d+(?:\.\d+)?)", body)
        reset_match = re.search(r"resetInSec:\s*(-?\d+(?:\.\d+)?)", body)
        if not usage_match or not reset_match:
            continue
        usage = max(0.0, float(usage_match.group(1)))
        reset_seconds = max(0.0, float(reset_match.group(1)))
        return {
            "remaining": max(0.0, min(100.0, 100.0 - usage)),
            "resetAt": int(now_ms + reset_seconds * 1000),
        }
    return None


def collect_opencode(env):
    workspace_id = env.get("OPENCODE_GO_WORKSPACE_ID", "").strip()
    cookie = env.get("OPENCODE_GO_AUTH_COOKIE", "").strip()
    if not workspace_id:
        return provider_result("opencode-go", error="请设置 OPENCODE_GO_WORKSPACE_ID 以启用 OpenCode Go")
    if not cookie:
        return provider_result("opencode-go", error="请设置 OPENCODE_GO_AUTH_COOKIE 以启用 OpenCode Go")
    url = "https://opencode.ai/workspace/" + urllib.parse.quote(workspace_id, safe="") + "/go"
    try:
        raw = get_url(
            url,
            {"Accept": "text/html", "Cookie": build_opencode_cookie(cookie), "User-Agent": "Mozilla/5.0 Quota-Glance/1.1.0"},
            env,
            timeout=15,
        )
        html = raw.decode("utf-8", errors="replace")
    except (OSError, urllib.error.URLError, UnicodeError):
        return provider_result("opencode-go", error="OpenCode Go 页面暂不可用")
    now_ms = int(time.time() * 1000)
    labels = [("rolling", "5小时"), ("weekly", "7天"), ("monthly", "月度")]
    metrics = []
    for key, label in labels:
        window = parse_opencode_window(html, key + "Usage", now_ms)
        if window:
            remain = window["remaining"]
            metrics.append(metric(label, f"{remain:.0f}%", remain, "", window["resetAt"]))
    if not metrics:
        return provider_result("opencode-go", error="无法读取 OpenCode Go 额度；请检查工作区和登录 Cookie")
    long_term = [item["progress"] for item in metrics if item["label"] in ("7天", "月度") and item["progress"] is not None]
    panel_value = f"{min(long_term) * 100:.0f}%" if long_term else metrics[0]["value"]
    return provider_result("opencode-go", True, metrics=metrics, panel_value=panel_value)


def format_balance(currency, amount):
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        value = Decimal("0")
    if not value.is_finite():
        value = Decimal("0")
    symbol = {"CNY": "¥", "USD": "$"}.get(currency, f"{currency} ")
    return f"{symbol}{value:,.2f}"


def collect_deepseek(env):
    api_key = env.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return provider_result("deepseek", error="请设置 DEEPSEEK_API_KEY 以启用 DeepSeek")
    try:
        raw = get_url(
            "https://api.deepseek.com/user/balance",
            {"Accept": "application/json", "Authorization": f"Bearer {api_key}", "User-Agent": "Quota-Glance/Plasma-1.1.0"},
            env,
        )
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError):
        return provider_result("deepseek", error="DeepSeek 余额暂不可用")
    balances = [record(item) for item in record(payload).get("balance_infos", []) if isinstance(item, dict)]
    if not balances:
        return provider_result("deepseek", error="DeepSeek 暂无余额数据")
    selected = next((item for item in balances if Decimal(str(item.get("total_balance", 0) or 0)) > 0), balances[0])
    metrics = []
    details = []
    for item in balances:
        currency = str(item.get("currency") or "--")
        balance = item.get("total_balance", "0")
        metrics.append(metric(currency, format_balance(currency, balance)))
        granted = format_balance(currency, item.get("granted_balance", "0"))
        topped_up = format_balance(currency, item.get("topped_up_balance", "0"))
        details.append(f"赠送余额 {granted} · 充值余额 {topped_up}")
    subtitle = "账户可用" if record(payload).get("is_available") else "账户不可用"
    panel_value = format_balance(str(selected.get("currency") or "--"), selected.get("total_balance", "0"))
    return provider_result(
        "deepseek", True, subtitle=subtitle,
        metrics=metrics, details=details, panel_value=panel_value,
    )


COLLECTORS = {
    "codex": collect_codex,
    "copilot": collect_copilot,
    "zai": collect_zai,
    "opencode-go": collect_opencode,
    "deepseek": collect_deepseek,
}


def main():
    env = load_environment()
    for key in ALLOWED_ENV:
        if key in env:
            os.environ[key] = env[key]
    requested = next((arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--providers=")), "")
    selected = [item for item in requested.split(",") if item in COLLECTORS]
    results = []
    for provider_id in PROVIDERS:
        if provider_id in selected:
            try:
                results.append(COLLECTORS[provider_id](env))
            except Exception:
                results.append(provider_result(provider_id, error=f"{PROVIDERS[provider_id][0]} 数据暂不可用"))
    sys.stdout.write(json.dumps({"providers": results, "updatedAt": int(time.time() * 1000)}, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
