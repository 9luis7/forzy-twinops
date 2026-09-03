"""Sanitized domain errors for the administrative RAG boundary."""


class RagAdminError(RuntimeError):
    """Base class whose message is safe to expose as a stable error code."""


class CorpusNotFoundError(RagAdminError):
    def __init__(self) -> None:
        super().__init__("corpus_not_found")


class CorpusCompatibilityError(RagAdminError):
    def __init__(self) -> None:
        super().__init__("corpus_incompatible")


class CorpusConflictError(RagAdminError):
    def __init__(self, code: str = "corpus_conflict") -> None:
        super().__init__(code)


class InvalidAdminInputError(RagAdminError):
    def __init__(self, code: str = "invalid_admin_input") -> None:
        super().__init__(code)

