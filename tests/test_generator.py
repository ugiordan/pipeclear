import pytest
from pathlib import Path
from src.generator import PipelineGenerator
from src.analyzer import NotebookAnalyzer


def test_generate_component_from_cells():
    """Test generating a KFP component from notebook cells."""
    code_cells = [
        "import pandas as pd",
        "df = pd.read_csv('data.csv')",
        "df_clean = df.dropna()"
    ]

    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="data_preprocessing",
        code_cells=code_cells,
        packages=['pandas']
    )

    assert '@dsl.component' in component_code
    assert 'def data_preprocessing' in component_code
    assert 'import pandas as pd' in component_code


def test_generate_pipeline_from_notebook():
    """Test generating full pipeline from notebook."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    generator = PipelineGenerator()
    pipeline_code = generator.generate_pipeline(
        analyzer=analyzer,
        pipeline_name="simple_pipeline"
    )

    assert '@dsl.pipeline' in pipeline_code
    assert 'def simple_pipeline' in pipeline_code
    assert 'from kfp import dsl' in pipeline_code


def test_sanitize_pipeline_name_starting_with_number():
    """Test that pipeline names starting with numbers are sanitized."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="1_simple_success",
        code_cells=["print('hello')"],
        packages=[]
    )
    assert 'def 1_' not in component_code
    assert 'def pipeline_1_simple_success' in component_code


def test_sanitize_pipeline_name_with_hyphens():
    """Test that pipeline names with hyphens are sanitized."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="my-cool-pipeline",
        code_cells=["print('hello')"],
        packages=[]
    )
    assert 'def my_cool_pipeline' in component_code


def test_sanitize_pipeline_name_normal():
    """Test that valid pipeline names are unchanged."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="valid_name",
        code_cells=["print('hello')"],
        packages=[]
    )
    assert 'def valid_name' in component_code
