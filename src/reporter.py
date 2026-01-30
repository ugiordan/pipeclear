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
                               f"largest available GPU ({max_gpu_memory}GB).",
                    'suggestion': f"💡 Fix: Use model.load_in_8bit=True (reduces to ~{required_vram/2:.0f}GB) "
                                 f"or device_map='auto' for model parallelism",
                    'time_impact': "Would fail after model loading (~5-10 minutes)"
                })
        else:
            # Show warnings for large models even without cluster info
            if required_vram > 80:  # Larger than A100
                issues.append({
                    'severity': 'critical',
                    'category': 'resource',
                    'message': f"Large model detected: {required_vram}GB VRAM estimated. "
                               f"Exceeds most single GPUs (A100 = 80GB).",
                    'suggestion': f"💡 Fix: Use 8-bit quantization (model.load_in_8bit=True) "
                                 f"or multi-GPU with device_map='auto'",
                    'time_impact': "Would likely fail with OOM error after 5-10 minutes"
                })
            elif required_vram > 40:  # Larger than A6000
                issues.append({
                    'severity': 'warning',
                    'category': 'resource',
                    'message': f"Medium-large model: {required_vram}GB VRAM estimated. "
                               f"Requires A100 (80GB) or larger GPU.",
                    'suggestion': f"💡 Tip: Ensure cluster has A100 GPUs available, or use quantization",
                    'time_impact': "May fail on smaller GPUs (V100/A6000)"
                })
            elif required_vram > 16:  # Show info for medium models
                issues.append({
                    'severity': 'warning',
                    'category': 'resource',
                    'message': f"GPU required: {required_vram}GB VRAM estimated. "
                               f"Ensure appropriate GPU is allocated.",
                    'suggestion': f"💡 Tip: A6000 (48GB) or A100 (80GB) recommended",
                    'time_impact': "May fail on smaller GPUs (T4/V100)"
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
                           f"{', '.join(report['unavailable'])}.",
                'suggestion': f"💡 Fix: Package custom libraries in container image "
                             f"or make available via PVC/git clone",
                'time_impact': "Would fail at import time (first few seconds of pipeline run)"
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
            secret_type = secret['type'].replace('_', ' ').title()
            issues.append({
                'severity': 'critical',
                'category': 'security',
                'message': f"Line {secret['line']}: Hardcoded {secret_type} detected.",
                'suggestion': f"💡 Fix: Use os.getenv('{secret_type.upper().replace(' ', '_')}') "
                             f"and store in OpenShift Secret",
                'time_impact': "Security risk - credentials exposed in pipeline code/logs"
            })

        for path in report['hardcoded_paths']:
            issues.append({
                'severity': 'warning',
                'category': 'portability',
                'message': f"Line {path['line']}: Hardcoded absolute path '{path['value']}'.",
                'suggestion': f"💡 Fix: Use parameter or PVC mount (path would not exist in container)",
                'time_impact': "Would fail when path doesn't exist (~seconds into execution)"
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

        # Estimate time saved
        time_saved_minutes = self._estimate_time_saved(all_issues)
        summary['time_saved_minutes'] = time_saved_minutes
        summary['time_saved_human'] = self._format_time_saved(time_saved_minutes)

        return {
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'issues': all_issues,
        }

    def _estimate_time_saved(self, issues: List[Dict]) -> int:
        """Estimate time saved by catching issues early.

        Args:
            issues: List of detected issues

        Returns:
            Estimated minutes saved
        """
        time_saved = 0
        for issue in issues:
            # Estimate based on severity and type
            if issue['severity'] == 'critical':
                if 'resource' in issue['category']:
                    time_saved += 30  # OOM failures happen after loading/training
                elif 'security' in issue['category']:
                    time_saved += 60  # Security issues take longer to debug
                else:
                    time_saved += 15
            elif issue['severity'] == 'warning':
                time_saved += 5  # Warnings still save debugging time

        return max(time_saved, 3)  # At minimum, 3 minutes saved from validation

    def _format_time_saved(self, minutes: int) -> str:
        """Format time saved in human-readable form.

        Args:
            minutes: Minutes saved

        Returns:
            Human-readable time string
        """
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            if mins > 0:
                return f"{hours}h {mins}min"
            return f"{hours}h"
        return f"{minutes}min"
