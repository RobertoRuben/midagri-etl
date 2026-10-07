from app.modules.common.exception.exception_rfc_schema import InvalidParam


class ProblemDetailsException(Exception):
    def __init__(
        self,
        title: str,
        status: int,
        detail: str,
        type: str = "about:blank",
        instance: str | None = None,
        invalid_params: list[InvalidParam] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.type = type
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.invalid_params = invalid_params
        self.headers = headers
        super().__init__(detail)
