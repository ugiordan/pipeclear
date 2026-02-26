"""Integration tests for end-to-end workflows."""
import pytest
from pathlib import Path
import json

from src.analyzer import NotebookAnalyzer
from src.validators.resource import ResourceEstimator
from src.validators.dependency import DependencyValidator
from src.validators.security import SecurityScanner
from src.reporter import IssueReporter
from src.generator import PipelineGenerator


def test_end_to_end_simple_notebook():
    """Test complete flow with simple notebook (should pass)."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")

    # Analyze
    analyzer = NotebookAnalyzer(notebook_path)
    assert len(analyzer.get_code_cells()) == 3

    # Validate
    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    # Report
    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    })

    # Should have no critical issues
    assert report['summary']['critical'] == 0
    assert 'time_saved_human' in report['summary']

    # Generate pipeline
    generator = PipelineGenerator()
    pipeline_code = generator.generate_pipeline(analyzer, "test_pipeline")

    assert '@dsl.pipeline' in pipeline_code
    assert 'def test_pipeline' in pipeline_code
    assert 'from kfp import dsl' in pipeline_code


def test_end_to_end_llm_notebook():
    """Test complete flow with LLM notebook (should have resource warnings)."""
    notebook_path = Path("tests/fixtures/llm_notebook.ipynb")

    # Analyze
    analyzer = NotebookAnalyzer(notebook_path)

    # Validate
    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    # Report
    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    })

    # Should have GPU requirements detected
    assert resource_report['gpu_required'] is True
    assert resource_report['estimated_vram_gb'] > 0

    # Should have warnings about resource usage
    assert report['summary']['total'] > 0


def test_end_to_end_secrets_notebook():
    """Test complete flow with secrets (should have critical issues)."""
    notebook_path = Path("tests/fixtures/secrets_notebook.ipynb")

    # Analyze
    analyzer = NotebookAnalyzer(notebook_path)

    # Validate
    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    # Report
    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    })

    # Should have critical security issues
    assert report['summary']['critical'] > 0

    # Should have detected secrets
    assert len(security_report['secrets']) > 0
    assert len(security_report['hardcoded_paths']) > 0

    # Issues should have suggestions
    for issue in report['issues']:
        if issue['severity'] == 'critical':
            assert 'suggestion' in issue
            assert 'time_impact' in issue


def test_pipeline_generation_is_valid_python():
    """Test that generated pipeline is syntactically valid Python."""
    notebook_path = Path("tests/fixtures/simple_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    generator = PipelineGenerator()
    pipeline_code = generator.generate_pipeline(analyzer, "valid_pipeline")

    # Try to compile the generated code
    try:
        compile(pipeline_code, '<string>', 'exec')
        valid = True
    except SyntaxError:
        valid = False

    assert valid, "Generated pipeline should be valid Python"


def test_time_savings_calculation():
    """Test that time savings are calculated correctly."""
    reporter = IssueReporter()

    # Test with critical resource issue
    issues = [{
        'severity': 'critical',
        'category': 'resource',
        'message': 'Test'
    }]
    time_saved = reporter._estimate_time_saved(issues)
    assert time_saved >= 30  # Critical resource issues save at least 30min

    # Test with security issue
    issues = [{
        'severity': 'critical',
        'category': 'security',
        'message': 'Test'
    }]
    time_saved = reporter._estimate_time_saved(issues)
    assert time_saved >= 60  # Security issues take longer to debug

    # Test with warnings
    issues = [{
        'severity': 'warning',
        'category': 'portability',
        'message': 'Test'
    }]
    time_saved = reporter._estimate_time_saved(issues)
    assert time_saved >= 3  # Minimum 3 minutes


def test_fix_suggestions_present():
    """Test that all critical issues have fix suggestions."""
    notebook_path = Path("tests/fixtures/secrets_notebook.ipynb")
    analyzer = NotebookAnalyzer(notebook_path)

    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    })

    # All critical issues should have suggestions
    for issue in report['issues']:
        if issue['severity'] == 'critical':
            assert 'suggestion' in issue, f"Critical issue missing suggestion: {issue['message']}"
            assert issue['suggestion'].startswith('💡'), "Suggestion should start with lightbulb"


def test_image_validator_integrated():
    """Test that image validation is integrated into the full report."""
    from src.reporter import IssueReporter
    reporter = IssueReporter()

    all_reports = {
        'resource': {'gpu_required': False, 'estimated_vram_gb': 0, 'models': []},
        'dependency': {'available': ['pandas'], 'unavailable': [], 'unknown': []},
        'security': {'secrets': [], 'hardcoded_paths': []},
        'image': [{'severity': 'critical', 'category': 'image',
                   'message': 'Base image not accessible: fake-image:latest',
                   'suggestion': 'Fix: Use accessible image',
                   'time_impact': 'Would fail with ImagePullBackOff'}],
    }

    report = reporter.generate_report(all_reports)
    assert report['summary']['critical'] == 1
    assert any(i['category'] == 'image' for i in report['issues'])
