class DuplicateEnsayoError(Exception):
    """Raised when trying to create an ensayo that already exists"""
    pass


class EnsayoNotFoundError(Exception):
    """Raised when an ensayo is not found"""
    pass
