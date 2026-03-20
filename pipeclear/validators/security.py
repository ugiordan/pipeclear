"""Security scanning for secrets and hardcoded values."""
import re
from typing import List, Dict


class SecurityScanner:
    """Scans code for security issues and hardcoded values."""

    # Regex patterns for common secrets
    PATTERNS = {
        'aws_access_key': r'AKIA[0-9A-Z]{16}',
        'aws_secret_key': r'(?i)(?:aws_secret_access_key|aws_secret_key|secret_key)\s*[=:]\s*["\']?([A-Za-z0-9/+=]{40})["\']?',
        'github_token': r'ghp_[a-zA-Z0-9]{36}',
        'openai_key': r'sk-[a-zA-Z0-9]{32,}',
        'huggingface_token': r'hf_[a-zA-Z0-9]{32,}',
    }

    def detect_secrets(self, code: str) -> List[Dict]:
        """Detect potential secrets in code.

        Args:
            code: Python source code

        Returns:
            List of detected secrets with type and location
        """
        secrets = []

        for secret_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, code):
                # Get line number
                line_num = code[:match.start()].count('\n') + 1

                secrets.append({
                    'type': secret_type,
                    'value': match.group(0),
                    'line': line_num,
                    'start': match.start(),
                    'end': match.end()
                })

        return secrets

    def detect_hardcoded_paths(self, code: str) -> List[Dict]:
        """Detect hardcoded absolute file paths.

        Args:
            code: Python source code

        Returns:
            List of detected paths with location
        """
        paths = []

        # Patterns for absolute paths
        path_patterns = [
            r"['\"]/(Users|home)/[^'\"]+['\"]",  # Unix home paths
            r"['\"][A-Z]:\\\\.+?['\"]",  # Windows paths
        ]

        for pattern in path_patterns:
            for match in re.finditer(pattern, code):
                line_num = code[:match.start()].count('\n') + 1

                paths.append({
                    'value': match.group(0).strip("'\""),
                    'line': line_num,
                })

        return paths

    def analyze(self, analyzer) -> Dict:
        """Analyze notebook for security issues.

        Args:
            analyzer: NotebookAnalyzer instance

        Returns:
            Security scan report
        """
        report = {
            'secrets': [],
            'hardcoded_paths': [],
        }

        # Scan all code cells
        for code in analyzer.get_code_cells():
            secrets = self.detect_secrets(code)
            paths = self.detect_hardcoded_paths(code)

            report['secrets'].extend(secrets)
            report['hardcoded_paths'].extend(paths)

        return report
