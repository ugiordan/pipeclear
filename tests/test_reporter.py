import pytest
from src.reporter import IssueReporter


def test_format_resource_issues():
    """Test formatting resource estimation issues."""
    report_data = {
        'gpu_required': True,
        'estimated_vram_gb': 140,
        'models': [
            {
                'name': 'meta-llama/Llama-2-70b',
                'estimated_vram_gb': 140
            }
        ]
    }

    cluster_info = {
        'gpus': [
            {'type': 'A100', 'memory_gb': 80, 'available': 1}
        ]
    }

    reporter = IssueReporter()
    issues = reporter.format_resource_issues(report_data, cluster_info)

    assert len(issues) == 1
    assert issues[0]['severity'] == 'critical'
    assert '140' in issues[0]['message']


def test_format_dependency_issues():
    """Test formatting dependency validation issues."""
    report_data = {
        'available': ['pandas', 'numpy'],
        'unavailable': ['custom_module', 'internal_lib']
    }

    reporter = IssueReporter()
    issues = reporter.format_dependency_issues(report_data)

    assert len(issues) == 1
    assert issues[0]['severity'] == 'warning'
    assert 'custom_module' in issues[0]['message']


def test_format_security_issues():
    """Test formatting security scan issues."""
    report_data = {
        'secrets': [
            {'type': 'aws_access_key', 'line': 15, 'value': 'AKIA...'}
        ],
        'hardcoded_paths': [
            {'value': '/Users/user/data.csv', 'line': 23}
        ]
    }

    reporter = IssueReporter()
    issues = reporter.format_security_issues(report_data)

    assert len(issues) == 2
    assert any(i['severity'] == 'critical' for i in issues)
    assert any('Line 15' in i['message'] for i in issues)


def test_generate_full_report():
    """Test generating complete report."""
    all_reports = {
        'resource': {
            'gpu_required': False,
            'estimated_vram_gb': 0,
            'models': []
        },
        'dependency': {
            'available': ['pandas'],
            'unavailable': []
        },
        'security': {
            'secrets': [],
            'hardcoded_paths': []
        }
    }

    reporter = IssueReporter()
    report = reporter.generate_report(all_reports)

    assert 'summary' in report
    assert 'issues' in report
    assert report['summary']['critical'] == 0
