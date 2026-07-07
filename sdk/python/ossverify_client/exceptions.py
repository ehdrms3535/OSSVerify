class OSSVerifyError(Exception):
    """OSSVerify SDK 기본 에러."""

class OSSVerifyAPIError(OSSVerifyError):
    """서버가 에러 응답을 반환한 경우."""
    def __init__(self, code: str, message: str, status_code: int = 0):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status_code = status_code

class OSSVerifyAnalysisError(OSSVerifyError):
    """비동기 분석 작업이 실패한 경우."""

class OSSVerifyTimeoutError(OSSVerifyError):
    """분석 폴링 타임아웃."""
