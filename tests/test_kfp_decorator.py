import pytest
from unittest.mock import patch
import kfp.dsl as dsl
from pipeclear.kfp.decorator import validate


def test_validate_decorator_passes_clean_pipeline(tmp_path):
    """Decorated pipeline should compile normally when clean."""
    @validate(fail_on_critical=True)
    def clean_pipe():
        pass

    assert callable(clean_pipe)
    assert hasattr(clean_pipe, '_pipeclear_validated')


def test_validate_decorator_stores_config():
    """Decorator should store PipeClear config on the pipeline function."""
    @validate(fail_on_critical=True, allowed_registries=['registry.redhat.io'])
    def configured_pipe():
        pass

    assert configured_pipe._pipeclear_config['fail_on_critical'] is True
    assert configured_pipe._pipeclear_config['allowed_registries'] == ['registry.redhat.io']
