"""PipeClear - Pre-flight validation for Jupyter notebooks on RHOAI."""

__version__ = "0.2.0"

from pathlib import Path
from typing import Optional

from pipeclear.analyzer import NotebookAnalyzer
from pipeclear.validators.resource import ResourceEstimator
from pipeclear.validators.dependency import DependencyValidator
from pipeclear.validators.security import SecurityScanner
from pipeclear.validators.image import ImageValidator
from pipeclear.reporter import IssueReporter
from pipeclear.generator import PipelineGenerator


def analyze(notebook_path: str, base_image: str = None) -> dict:
    """Analyze a notebook and return a validation report.

    Args:
        notebook_path: Path to .ipynb file
        base_image: Optional base image to validate

    Returns:
        Validation report dictionary with 'summary' and 'issues' keys
    """
    analyzer = NotebookAnalyzer(Path(notebook_path))

    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    all_reports = {
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    }

    if base_image:
        all_reports['image'] = ImageValidator().validate_image(base_image)

    return IssueReporter().generate_report(all_reports)


def generate(
    notebook_path: str,
    output: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    base_image: str = "registry.access.redhat.com/ubi9/python-311:latest"
) -> str:
    """Generate a KFP pipeline from a notebook.

    Args:
        notebook_path: Path to .ipynb file
        output: Optional path to write generated pipeline code
        pipeline_name: Optional pipeline name (defaults to notebook filename)
        base_image: Base container image for pipeline components

    Returns:
        Generated pipeline Python code as string
    """
    path = Path(notebook_path)
    analyzer = NotebookAnalyzer(path)

    name = pipeline_name or path.stem
    generator = PipelineGenerator()
    code = generator.generate_pipeline(
        analyzer=analyzer,
        pipeline_name=name,
        base_image=base_image
    )

    if output:
        Path(output).write_text(code)

    return code
