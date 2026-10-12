"""Erros de domínio e tratamento global de exceções.

Toda resposta de erro segue o mesmo formato, pensado para o frontend exibir
mensagens amigáveis sem expor detalhes internos:

    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}
"""
import logging
import uuid
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("crm")


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Não foi possível processar a solicitação."

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        details: Optional[list[dict[str, Any]]] = None,
        headers: Optional[dict[str, str]] = None,
    ):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.headers = headers


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Sessão inválida ou expirada. Faça login novamente."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "Você não tem permissão para realizar esta ação."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Recurso não encontrado."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "A operação conflita com dados já existentes."


class AccountLocked(AppError):
    status_code = 423
    code = "account_locked"
    message = "Conta temporariamente bloqueada por excesso de tentativas. Tente novamente mais tarde."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, retry_after: int):
        super().__init__(
            f"Muitas tentativas em pouco tempo. Aguarde {retry_after} segundo(s) e tente novamente.",
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


_HTTP_MESSAGES = {
    401: ("unauthorized", "Sessão inválida ou expirada. Faça login novamente."),
    403: ("forbidden", "Você não tem permissão para realizar esta ação."),
    404: ("not_found", "Recurso não encontrado."),
    405: ("method_not_allowed", "Método não permitido para este recurso."),
    429: ("rate_limited", "Muitas requisições. Tente novamente em instantes."),
}

# Constraints conhecidas do schema -> mensagens amigáveis.
_CONSTRAINT_MESSAGES = {
    "users_email_key": "Este e-mail já está em uso.",
    "companies_cnpj_key": "Já existe uma empresa cadastrada com este CNPJ.",
    "uq_contacts_primary_per_company": "Esta empresa já possui um contato principal.",
    "uq_stage_name": "Já existe uma etapa com este nome neste funil.",
    "pipelines_name_key": "Já existe um funil com este nome.",
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _body(request: Request, code: str, message: str, details: Optional[list] = None) -> dict:
    err: dict[str, Any] = {"code": code, "message": message, "request_id": _request_id(request)}
    if details:
        err["details"] = details
    return {"error": err}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Gera X-Request-ID (rastreabilidade) e adiciona cabeçalhos de segurança básicos."""

    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(request, exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        code, message = _HTTP_MESSAGES.get(exc.status_code, ("http_error", "Não foi possível concluir a solicitação."))
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(request, code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
                "message": str(err.get("msg", "Valor inválido.")).removeprefix("Value error, "),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_body(
                request, "validation_error",
                "Alguns campos estão inválidos. Revise as informações e tente novamente.", details,
            ),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, exc: IntegrityError):
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        message = _CONSTRAINT_MESSAGES.get(
            constraint or "", "Não foi possível salvar: os dados conflitam com registros existentes."
        )
        logger.warning("integrity_error constraint=%s request_id=%s", constraint, _request_id(request))
        return JSONResponse(status_code=409, content=_body(request, "constraint_violation", message))

    @app.exception_handler(OperationalError)
    async def handle_db_down(request: Request, exc: OperationalError):
        logger.error("database_unavailable request_id=%s", _request_id(request), exc_info=exc)
        return JSONResponse(
            status_code=503,
            content=_body(request, "service_unavailable", "Serviço temporariamente indisponível. Tente novamente em instantes."),
            headers={"Retry-After": "5"},
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(request: Request, exc: SQLAlchemyError):
        logger.error("database_error request_id=%s", _request_id(request), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_body(request, "internal_error", "Ocorreu um erro inesperado. Nossa equipe já foi notificada."),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.error("unhandled_exception request_id=%s", _request_id(request), exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_body(request, "internal_error", "Ocorreu um erro inesperado. Nossa equipe já foi notificada."),
        )
