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
