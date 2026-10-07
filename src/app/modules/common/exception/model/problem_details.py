from app.modules.common.exception.exception_rfc_schema import InvalidParam

from .base_exception import ProblemDetailsException


class NotFoundException(ProblemDetailsException):
    """HTTP 404"""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=404, title="Resource Not Found", detail=detail, instance=instance)


class BadRequestException(ProblemDetailsException):
    """HTTP 400 - General bad requests or business rules violations."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=400, title="Bad Request", detail=detail, instance=instance)


class InvalidParametersException(ProblemDetailsException):
    """HTTP 400 - Specifically for invalid fields or input parameters."""

    def __init__(self, detail: str, invalid_params: list[InvalidParam], instance: str | None = None):
        super().__init__(
            status=400,
            title="Invalid Request Parameters",
            detail=detail,
            instance=instance,
            invalid_params=invalid_params,
        )


class UnauthorizedException(ProblemDetailsException):
    """HTTP 401"""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=401, title="Unauthorized", detail=detail, instance=instance)


class ForbiddenException(ProblemDetailsException):
    """HTTP 403"""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=403, title="Forbidden", detail=detail, instance=instance)


class ConflictException(ProblemDetailsException):
    """HTTP 409"""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=409, title="Conflict", detail=detail, instance=instance)


class UploadIndexesConflictException(ConflictException):
    """HTTP 409 que nombra índices de una sesión de subida directa en un campo `indexes`.

    Los índices también van en `detail`, pero ahí son texto para una persona: el cliente que se recupera
    solo —reemitir las URLs que faltan, quitar las que ya subió— necesita leerlos sin parsear frases
    (SPEC-jobs-direct-upload §5.4 y §5.6).
    """

    def __init__(self, detail: str, indexes: list[int], instance: str | None = None):
        super().__init__(detail=detail, instance=instance)
        self.indexes = sorted(indexes)


class PayloadTooLargeException(ProblemDetailsException):
    """HTTP 413 - El cuerpo supera el tamaño máximo admitido por la ruta."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=413, title="Payload Too Large", detail=detail, instance=instance)


class QuotaExceededException(ProblemDetailsException):
    """HTTP 402 - Cupo mensual de ejecuciones del plan agotado."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=402, title="Quota Exceeded", detail=detail, instance=instance)


class UpstreamProviderException(ProblemDetailsException):
    """HTTP 502 - Fallo al invocar un proveedor externo (LLM, OCR, etc.)."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=502, title="Upstream Provider Error", detail=detail, instance=instance)


class UnprocessableEntityException(ProblemDetailsException):
    """HTTP 422 - La solicitud es sintacticamente valida pero semanticamente incorrecta."""

    def __init__(self, detail: str, instance: str | None = None):
        super().__init__(status=422, title="Unprocessable Entity", detail=detail, instance=instance)


class TooManyRequestsException(ProblemDetailsException):
    """HTTP 429 - Se excedió el límite de consultas permitidas por ventana de tiempo."""

    def __init__(self, detail: str, retry_after: int, instance: str | None = None):
        super().__init__(
            status=429,
            title="Too Many Requests",
            detail=detail,
            instance=instance,
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after
