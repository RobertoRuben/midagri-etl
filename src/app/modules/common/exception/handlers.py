import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modules.common.exception.exception_rfc_schema import InvalidParam, ProblemDetailsModel
from app.modules.common.exception.model.base_exception import ProblemDetailsException

logger = logging.getLogger("app.exception")


async def problem_details_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, ProblemDetailsException)
    logger.warning(
        "%s %s -> %s %s: %s",
        request.method,
        request.url.path,
        exc.status,
        exc.title,
        exc.detail,
    )
    body = ProblemDetailsModel(
        type=exc.type,
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        instance=exc.instance or request.url.path,
        invalid_params=exc.invalid_params,
        retry_after=getattr(exc, "retry_after", None),
        indexes=getattr(exc, "indexes", None),
    )
    return JSONResponse(
        status_code=exc.status,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
        headers=exc.headers,
    )


async def http_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    logger.warning(
        "%s %s -> %s HTTP Error: %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    body = ProblemDetailsModel(
        title="HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail),
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    invalid_params = [
        InvalidParam(name=".".join(str(part) for part in error["loc"]), reason=error["msg"]) for error in exc.errors()
    ]
    logger.warning(
        "%s %s -> 422 Unprocessable Entity: %s",
        request.method,
        request.url.path,
        invalid_params,
    )
    body = ProblemDetailsModel(
        title="Unprocessable Entity",
        status=422,
        detail="La solicitud contiene parámetros inválidos.",
        instance=request.url.path,
        invalid_params=invalid_params,
    )
    return JSONResponse(
        status_code=422,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "%s %s -> 500 Internal Server Error",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    body = ProblemDetailsModel(
        title="Internal Server Error",
        status=500,
        detail="Ocurrió un error interno inesperado.",
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ProblemDetailsException, problem_details_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
