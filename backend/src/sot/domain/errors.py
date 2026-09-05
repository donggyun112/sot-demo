class DomainError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(code)


__all__ = ["DomainError"]
