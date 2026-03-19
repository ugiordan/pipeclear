"""Test PipeClear against real RHOAI notebook-generated pipelines."""
import pytest
from pathlib import Path
from pipeclear import analyze, generate


NOTEBOOKS_DIR = Path(__file__).parent.parent / 'examples' / 'rhoai_real_notebooks'


@pytest.fixture
def notebooks():
    """Get all real RHOAI notebooks."""
    nbs = list(NOTEBOOKS_DIR.glob('*.ipynb'))
    if not nbs:
        pytest.skip("No real RHOAI notebooks found")
    return nbs


def test_analyze_real_notebooks(notebooks):
    """All real notebooks should be analyzable without errors."""
    for nb in notebooks:
        report = analyze(str(nb))
        assert 'summary' in report
        assert 'critical' in report['summary']


def test_generate_from_clean_notebook(notebooks, tmp_path):
    """Clean notebooks should generate valid pipeline code."""
    clean = [nb for nb in notebooks if 'distributed' not in nb.name]
    assert len(clean) > 0

    for nb in clean[:3]:
        output = tmp_path / f"{nb.stem}_pipeline.py"
        code = generate(str(nb), output=str(output))
        assert output.exists()
        assert 'dsl.pipeline' in code
        assert 'dsl.component' in code


def test_analyze_catches_real_security_issue(notebooks):
    """The distributed training notebook should flag the hardcoded AWS key."""
    distributed = [nb for nb in notebooks if 'distributed' in nb.name]
    if not distributed:
        pytest.skip("Distributed training notebook not found")

    report = analyze(str(distributed[0]))
    assert report['summary']['critical'] > 0
    assert any('aws' in str(issue).lower() or 'secret' in str(issue).lower()
               for issue in report.get('issues', []))
