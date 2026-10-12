from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Every expected failure. Rendered as {"error": {"code", "message"}}."""

    status_code = 400

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class NotFound(AppError):
    status_code = 404

    def __init__(self, what: str) -> None:
        super().__init__("not_found", f"{what} not found")


class Forbidden(AppError):
    status_code = 403

    def __init__(self, message: str = "Not allowed") -> None:
        super().__init__("forbidden", message)


class Unauthorized(AppError):
    status_code = 401

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__("unauthorized", message)


class Conflict(AppError):
    status_code = 409


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "details": jsonable_errors(exc),
                }
            },
        )


def jsonable_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    return [{"loc": list(e.get("loc", [])), "msg": str(e.get("msg", ""))} for e in exc.errors()]
