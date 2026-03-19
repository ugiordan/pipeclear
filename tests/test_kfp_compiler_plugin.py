# tests/test_kfp_compiler_plugin.py
import pytest
from unittest.mock import patch, MagicMock
from pipeclear.kfp.compiler import PipeClearCompiler


def test_compiler_passes_clean_pipeline(tmp_path):
    """Compiler should compile when no critical issues found."""
    import kfp.dsl as dsl

    @dsl.component(base_image="registry.access.redhat.com/ubi9/python-311:latest")
    def dummy():
        print("hello")

    @dsl.pipeline(name="clean-pipeline")
    def clean_pipe():
        dummy()

    output = tmp_path / "pipeline.yaml"
    compiler = PipeClearCompiler()
    compiler.compile(pipeline_func=clean_pipe, package_path=str(output))
    assert output.exists()


def test_compiler_blocks_on_critical_issues(tmp_path):
    """Compiler should raise when critical issues detected in generated spec."""
    import kfp.dsl as dsl

    @dsl.component(base_image="registry.access.redhat.com/ubi9/python-311:latest")
    def dummy():
        print("hello")

    @dsl.pipeline(name="test-pipeline")
    def test_pipe():
        dummy()

    output = tmp_path / "pipeline.yaml"
    compiler = PipeClearCompiler(fail_on_critical=True)

    # Mock validate_pipeline_spec to return critical issues
    with patch.object(compiler, 'validate_pipeline_spec', return_value={
        'critical': [{'message': 'Image uses mutable tag', 'severity': 'critical'}],
        'warnings': []
    }):
        with pytest.raises(SystemExit):
            compiler.compile(pipeline_func=test_pipe, package_path=str(output))
