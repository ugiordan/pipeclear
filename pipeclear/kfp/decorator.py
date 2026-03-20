"""PipeClear decorator for KFP pipeline functions."""


def validate(fail_on_critical=True, allowed_registries=None):
    """Decorator that marks a KFP pipeline for PipeClear validation at compile time.

    When used with PipeClearCompiler, the compiler will use these settings.
    Can also be used standalone to mark pipelines for validation.
    """
    def decorator(func):
        func._pipeclear_validated = True
        func._pipeclear_config = {
            'fail_on_critical': fail_on_critical,
            'allowed_registries': allowed_registries,
        }
        return func
    return decorator
