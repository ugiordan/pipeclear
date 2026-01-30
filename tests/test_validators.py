import pytest
from pathlib import Path
from src.validators.resource import ResourceEstimator


def test_detect_model_loading():
    """Test detecting HuggingFace model loading patterns."""
    code = "model = AutoModelForCausalLM.from_pretrained('meta-llama/Llama-2-7b')"

    estimator = ResourceEstimator()
    models = estimator.detect_models(code)

    assert len(models) == 1
    assert models[0]['name'] == 'meta-llama/Llama-2-7b'
    assert models[0]['type'] == 'huggingface'


def test_estimate_model_memory():
    """Test estimating memory requirements for known model."""
    estimator = ResourceEstimator()

    memory_gb = estimator.estimate_memory('meta-llama/Llama-2-7b', precision='fp16')

    # 7B params * 2 bytes/param * 1.5 overhead / 1GB = ~21GB
    assert 18 <= memory_gb <= 25


def test_full_notebook_resource_estimation():
    """Test full resource estimation from notebook."""
    notebook_path = Path("tests/fixtures/llm_notebook.ipynb")

    from src.analyzer import NotebookAnalyzer
    analyzer = NotebookAnalyzer(notebook_path)

    estimator = ResourceEstimator()
    report = estimator.analyze(analyzer)

    assert report['gpu_required'] is True
    assert report['estimated_vram_gb'] > 0


from src.validators.dependency import DependencyValidator


def test_extract_package_imports():
    """Test extracting package imports from code."""
    code = """
import pandas as pd
import torch
from sklearn.ensemble import RandomForest
import custom_local_module
"""

    validator = DependencyValidator()
    packages = validator.extract_imports(code)

    assert 'pandas' in packages
    assert 'torch' in packages
    assert 'sklearn' in packages


def test_check_pypi_availability():
    """Test checking if package is available on PyPI."""
    validator = DependencyValidator()

    # Well-known packages
    assert validator.is_on_pypi('pandas') is True
    assert validator.is_on_pypi('numpy') is True

    # Unlikely to exist
    assert validator.is_on_pypi('this-package-definitely-does-not-exist-xyz123') is False


def test_validate_dependencies():
    """Test full dependency validation."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")

    from src.analyzer import NotebookAnalyzer
    analyzer = NotebookAnalyzer(notebook_path)

    validator = DependencyValidator()
    report = validator.analyze(analyzer)

    assert 'pandas' in report['available']
    assert 'numpy' in report['available']


from src.validators.security import SecurityScanner


def test_detect_aws_credentials():
    """Test detecting AWS access keys."""
    code = "AWS_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'"

    scanner = SecurityScanner()
    secrets = scanner.detect_secrets(code)

    assert len(secrets) == 1
    assert secrets[0]['type'] == 'aws_access_key'


def test_detect_hardcoded_paths():
    """Test detecting hardcoded absolute paths."""
    code = """
model_path = '/Users/datascientist/models/my_model.pkl'
data_path = '/home/user/data.csv'
"""

    scanner = SecurityScanner()
    paths = scanner.detect_hardcoded_paths(code)

    assert len(paths) == 2
    assert any('/Users/' in p['value'] for p in paths)
    assert any('/home/' in p['value'] for p in paths)


def test_full_security_scan():
    """Test full security scan of notebook."""
    notebook_path = Path("tests/fixtures/secrets_notebook.ipynb")

    from src.analyzer import NotebookAnalyzer
    analyzer = NotebookAnalyzer(notebook_path)

    scanner = SecurityScanner()
    report = scanner.analyze(analyzer)

    assert len(report['secrets']) > 0
    assert len(report['hardcoded_paths']) > 0
