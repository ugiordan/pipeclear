import pytest
from pathlib import Path
from src.analyzer import NotebookAnalyzer


def test_load_notebook():
    """Test that we can load a simple notebook."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    assert analyzer.notebook is not None
    assert len(analyzer.cells) == 3


def test_extract_code_from_cells():
    """Test extracting code from notebook cells."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    code_cells = analyzer.get_code_cells()

    assert len(code_cells) == 3
    assert "import pandas as pd" in code_cells[0]
    assert "pd.read_csv" in code_cells[1]
    assert "df.dropna()" in code_cells[2]


def test_extract_imports():
    """Test extracting all import statements from notebook."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    imports = analyzer.extract_imports()

    assert 'pandas' in imports
    assert 'numpy' in imports
    assert len(imports) == 2
