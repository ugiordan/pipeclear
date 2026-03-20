import os
import tempfile
import pytest
from unittest.mock import patch
import kfp.dsl as dsl
from pipeclear.kfp.decorator import validate
from pipeclear.kfp.compiler import PipeClearCompiler


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


@dsl.component(base_image="registry.redhat.io/ubi9/python-311:1")
def clean_task_op():
    print("clean task")


def test_decorator_config_applied_by_compiler():
    """Test that PipeClearCompiler reads @validate decorator config."""
    @validate(fail_on_critical=False, allowed_registries=['registry.redhat.io'])
    @dsl.pipeline(name='decorated-pipeline')
    def my_pipeline():
        clean_task_op()

    pc = PipeClearCompiler(fail_on_critical=True, allowed_registries=None)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, 'pipeline.yaml')
        result = pc.compile(my_pipeline, output_path)

    # After compile, the decorator config should have overridden
    assert pc.fail_on_critical == False
    assert pc.allowed_registries == ['registry.redhat.io']
