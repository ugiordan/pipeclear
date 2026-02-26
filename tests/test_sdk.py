import pytest
from pathlib import Path


def test_analyze_function():
    """Test the public analyze() API."""
    from pipeclear import analyze

    report = analyze("tests/fixtures/simple_notebook.ipynb")
    assert 'summary' in report
    assert 'issues' in report
    assert 'timestamp' in report
    assert report['summary']['total'] >= 0


def test_analyze_notebook_with_issues():
    """Test analyze() returns issues for problematic notebook."""
    from pipeclear import analyze

    report = analyze("tests/fixtures/secrets_notebook.ipynb")
    assert report['summary']['critical'] > 0


def test_generate_function():
    """Test the public generate() API."""
    from pipeclear import generate
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as f:
        output_path = f.name

    try:
        code = generate("tests/fixtures/simple_notebook.ipynb", output=output_path)
        assert '@dsl.pipeline' in code
        assert os.path.exists(output_path)
    finally:
        os.unlink(output_path)
