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


def test_compiler_warns_on_many_tasks():
    """Compiler should warn when pipeline has many executors."""
    compiler = PipeClearCompiler(fail_on_critical=False)
    # Create spec with 60 executors
    executors = {f'exec-{i}': {'container': {'image': f'registry.redhat.io/img:{i}'}} for i in range(60)}
    spec = {'deploymentSpec': {'executors': executors}, 'root': {'dag': {'tasks': {}}}}
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['warnings']) > 0
    assert any('tasks' in w['message'].lower() for w in result['warnings'])


def test_compiler_blocks_excessive_tasks():
    """Compiler should block when pipeline has too many executors."""
    compiler = PipeClearCompiler(fail_on_critical=True)
    executors = {f'exec-{i}': {'container': {'image': f'registry.redhat.io/img:{i}'}} for i in range(110)}
    spec = {'deploymentSpec': {'executors': executors}, 'root': {'dag': {'tasks': {}}}}
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['critical']) > 0
    assert any('tasks' in c['message'].lower() or 'task' in c['message'].lower() for c in result['critical'])


def test_compiler_validates_allowed_registries():
    """Compiler should block images from non-allowed registries."""
    compiler = PipeClearCompiler(
        fail_on_critical=True,
        allowed_registries=['registry.redhat.io', 'quay.io']
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'docker.io/library/python:3.11'}},
            },
        },
    }
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['critical']) > 0
    assert any('allowed registry' in c['message'].lower() for c in result['critical'])
