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
