"""Dependency validation module."""
import ast
from typing import Set, Dict, List
import urllib.request
import urllib.error
import json


class DependencyValidator:
    """Validates Python package dependencies."""

    def extract_imports(self, code: str) -> Set[str]:
        """Extract package names from import statements.

        Args:
            code: Python source code

        Returns:
            Set of package names
        """
        packages = set()

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        package = alias.name.split('.')[0]
                        packages.add(package)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        package = node.module.split('.')[0]
                        packages.add(package)
        except SyntaxError:
            pass

        return packages

    def is_on_pypi(self, package_name: str) -> bool:
        """Check if package exists on PyPI.

        Args:
            package_name: Package name to check

        Returns:
            True if package exists on PyPI
        """
        url = f"https://pypi.org/pypi/{package_name}/json"

        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status == 200
        except urllib.error.HTTPError:
            return False
        except Exception:
            # Network error, timeout, etc - assume unavailable
            return False

    def analyze(self, analyzer) -> Dict:
        """Analyze notebook dependencies.

        Args:
            analyzer: NotebookAnalyzer instance

        Returns:
            Dependency validation report
        """
        all_imports = set()

        # Collect all imports from notebook
        for code in analyzer.get_code_cells():
            imports = self.extract_imports(code)
            all_imports.update(imports)

        # Categorize packages
        report = {
            'available': [],
            'unavailable': [],
            'unknown': [],
        }

        # Standard library packages (always available)
        stdlib = {
            'os', 'sys', 'json', 'pickle', 're', 'time', 'datetime',
            'pathlib', 'collections', 'itertools', 'functools', 'math',
            'random', 'logging', 'io', 'typing'
        }

        for package in all_imports:
            if package in stdlib:
                report['available'].append(package)
            else:
                # Check PyPI (expensive, so we'd cache in real implementation)
                if self.is_on_pypi(package):
                    report['available'].append(package)
                else:
                    report['unavailable'].append(package)

        return report
