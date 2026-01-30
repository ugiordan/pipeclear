"""Issue reporting and formatting module."""
from typing import Dict, List, Optional
from datetime import datetime


class IssueReporter:
    """Formats validation results into user-friendly reports."""

    def format_resource_issues(
        self,
        report: Dict,
        cluster_info: Optional[Dict] = None
    ) -> List[Dict]:
        """Format resource estimation into issues.

        Args:
            report: Resource estimation report
            cluster_info: Optional cluster GPU availability

        Returns:
            List of formatted issues
        """
        issues = []

        if not report['gpu_required']:
            return issues

        required_vram = report['estimated_vram_gb']

        # Check against cluster availability if provided
        if cluster_info and 'gpus' in cluster_info:
            max_gpu_memory = max(
                (gpu['memory_gb'] for gpu in cluster_info['gpus']),
                default=0
            )

            if required_vram > max_gpu_memory:
                issues.append({
                    'severity': 'critical',
                    'category': 'resource',
                    'message': f"Estimated VRAM requirement ({required_vram}GB) exceeds "
                               f"largest available GPU ({max_gpu_memory}GB). "
                               f"Model parallelism or quantization needed."
                })

        return issues

    def format_dependency_issues(self, report: Dict) -> List[Dict]:
        """Format dependency validation into issues.

        Args:
            report: Dependency validation report

        Returns:
            List of formatted issues
        """
        issues = []

        if report['unavailable']:
            issues.append({
                'severity': 'warning',
                'category': 'dependency',
                'message': f"Local/unavailable packages detected: "
                           f"{', '.join(report['unavailable'])}. "
                           f"Must be packaged with pipeline or made available."
            })

        return issues

    def format_security_issues(self, report: Dict) -> List[Dict]:
        """Format security scan into issues.

        Args:
            report: Security scan report

        Returns:
            List of formatted issues
        """
        issues = []

        for secret in report['secrets']:
            issues.append({
                'severity': 'critical',
                'category': 'security',
                'message': f"Line {secret['line']}: Hardcoded {secret['type']} detected. "
                           f"Use environment variables or OpenShift Secrets."
            })

        for path in report['hardcoded_paths']:
            issues.append({
                'severity': 'warning',
                'category': 'portability',
                'message': f"Line {path['line']}: Hardcoded absolute path '{path['value']}'. "
                           f"Parameterize or use PVC mount."
            })

        return issues

    def generate_report(
        self,
        all_reports: Dict,
        cluster_info: Optional[Dict] = None
    ) -> Dict:
        """Generate comprehensive validation report.

        Args:
            all_reports: Dictionary with 'resource', 'dependency', 'security' reports
            cluster_info: Optional cluster information

        Returns:
            Complete formatted report
        """
        all_issues = []

        # Collect issues from all validators
        all_issues.extend(
            self.format_resource_issues(
                all_reports['resource'],
                cluster_info
            )
        )
        all_issues.extend(
            self.format_dependency_issues(all_reports['dependency'])
        )
        all_issues.extend(
            self.format_security_issues(all_reports['security'])
        )

        # Count by severity
        summary = {
            'critical': sum(1 for i in all_issues if i['severity'] == 'critical'),
            'warning': sum(1 for i in all_issues if i['severity'] == 'warning'),
            'total': len(all_issues),
        }

        return {
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'issues': all_issues,
        }
