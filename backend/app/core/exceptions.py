class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code="NOT_FOUND",
            message=f"{resource} not found: {resource_id}",
            status_code=404,
        )


class ConflictError(AppError):
    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=409)


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(code="VALIDATION_ERROR", message=message, status_code=400)
