"""Only fixed vocabulary crosses the Runner / CLI boundary."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re

MESSAGES = {
    "auth_required": "会话不可用；请执行 login。",
    "refresh_uncertain": "续期结果不确定；勿重试旧凭据，请重新 login。",
    "invalid_client": "检查注册 client 与安装配置，不要自动重注册。",
    "permission_denied": "检查授权范围与 client。",
    "ineligible": "请检查订阅资格、区域与工作区策略。",
    "auth_invalid": "请检查当前会话；确认失效后重新登录。",
    "admission_denied": "上游拒绝访问；检查资格及授权。",
    "stale_attempt": "会话已变更，丢弃本次结果。",
    "registration_mismatch": "不允许用不同注册覆盖此目录。",
    "usage_paused": "请检查 https://chatgpt.com/settings/usage 后执行 resume。",
    "unsupported_input": "仅支持 schema 1 的纯文本与助手拒答。",
    "unsupported_request": "上游不支持所请求的能力。",
    "route_mismatch": "请检查官方端点、方法与宿主配置。",
    "stream_failed": "未收到有效完整回复，部分文本已丢弃。",
    "storage_failed": "检查存储、权限及文件格式；若续期写入失败须重新 login。",
    "storage_busy": "凭据锁等待超时，请稍后重试。",
    "rate_limited": "请求受限，请稍后重试。",
    "temporarily_unavailable": "服务暂不可用，请稍后重试。",
    "transport": "网络或 TLS 失败，请检查连接。",
    "upstream": "官方服务未返回有效结果。",
    "invalid_login": "授权验证失败或超时，未提交会话。",
    "invalid_config": "配置或输入参数无效。",
}
CODES = {
    "subscription_sharing_" + k: v
    for k, v in {
        "usage_limit_exceeded": "usage_paused",
        "user_not_eligible": "ineligible",
        "usage_unavailable": "temporarily_unavailable",
        "user_unavailable": "temporarily_unavailable",
        "unsupported_capability": "unsupported_request",
        "route_not_supported": "route_mismatch",
        "invalid_user": "auth_invalid",
    }.items()
}
CODES.update(
    user_unavailable="temporarily_unavailable",
    chatpass_v2_scope_not_authorized="permission_denied",
    invalid_authorization_context="permission_denied",
)


class Error(Exception):
    def __init__(
        self,
        category,
        *,
        status=None,
        code=None,
        request_id=None,
        param=None,
        delay=None,
    ):
        self.category = category
        self.http_status = status
        self.upstream_code = code if isinstance(code, str) and code in CODES else None
        self.request_id = (
            request_id
            if isinstance(request_id, str)
            and re.fullmatch(r"req_[a-zA-Z0-9-]{1,64}", request_id)
            else None
        )
        self.upstream_param = (
            param if param in ("input", "model", "stream", "store") else None
        )
        self.retry_after_seconds = delay
        fields = [
            str(x)
            for x in (status, self.upstream_code, self.upstream_param, self.request_id)
            if x is not None
        ]
        super().__init__(
            " ".join(
                [f"[chatgpt_subscription:{category}]", MESSAGES[category], *fields]
            )
        )

    @property
    def exit_code(self):
        groups = {
            2: ("invalid_client", "invalid_config"),
            3: (
                "auth_required",
                "refresh_uncertain",
                "invalid_login",
                "stale_attempt",
                "registration_mismatch",
                "permission_denied",
                "admission_denied",
                "auth_invalid",
                "ineligible",
            ),
            4: ("unsupported_input", "unsupported_request", "route_mismatch"),
            5: ("usage_paused", "rate_limited", "temporarily_unavailable"),
            7: ("storage_failed", "storage_busy"),
        }
        return next((n for n, c in groups.items() if self.category in c), 6)


def retry_after(value):
    if not value:
        return None
    try:
        if value.isascii() and value.isdecimal():
            return min(int(value), 10**15)
        return max(
            0,
            math.ceil(
                (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds()
            ),
        )
    except (ValueError, OverflowError, TypeError):
        return None


def classify(status, body, headers, *, stream=False):
    data = body.get("error", body) if isinstance(body, dict) else {}
    data = data if isinstance(data, dict) else {}
    code = data.get("code")
    category = CODES.get(code) if isinstance(code, str) else None
    if not category:
        category = (
            "stream_failed"
            if stream
            else {
                401: "admission_denied",
                403: "admission_denied",
                429: "rate_limited",
            }.get(status, "upstream")
        )
    return Error(
        category,
        status=status,
        code=code,
        param=data.get("param"),
        request_id=headers.get("x-request-id"),
        delay=retry_after(headers.get("retry-after")),
    )
