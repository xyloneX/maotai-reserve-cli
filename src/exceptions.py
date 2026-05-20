"""业务异常。"""


class IMaotaiError(Exception):
    pass


class ConfigError(IMaotaiError):
    pass


class TokenExpiredError(IMaotaiError):
    pass


class SessionNotReadyError(IMaotaiError):
    """非申购时段或 sessionId 尚未开放。"""


class RateLimitError(IMaotaiError):
    """接口限流 HTTP 429。"""


class AuthError(IMaotaiError):
    """登录 / 验证码错误。"""
