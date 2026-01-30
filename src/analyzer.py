"""Notebook analysis and parsing module."""
import ast
from pathlib import Path
from typing import Dict, List, Set
import nbformat
from nbformat.notebooknode import NotebookNode


def extract_defined_vars(code: str) -> Set[str]:
    """Extract variable names defined in code.

    Args:
        code: Python source code

    Returns:
        Set of variable names assigned in the code
    """
    defined = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
    except SyntaxError:
        pass
    return defined


def extract_used_vars(code: str) -> Set[str]:
    """Extract variable names used (referenced) in code.

    Args:
        code: Python source code

    Returns:
        Set of variable names referenced in the code
    """
    used = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)
    except SyntaxError:
        pass
    return used


class NotebookAnalyzer:
    """Analyzes Jupyter notebooks and extracts code structure."""

    def __init__(self, notebook_path: Path):
        """Initialize analyzer with notebook path.

        Args:
            notebook_path: Path to .ipynb file
        """
        self.notebook_path = Path(notebook_path)
        self.notebook = self._load_notebook()
        self.cells = self._extract_cells()

    def _load_notebook(self) -> NotebookNode:
        """Load notebook from file.

        Returns:
            Loaded notebook object
        """
        with open(self.notebook_path, 'r', encoding='utf-8') as f:
            return nbformat.read(f, as_version=4)

    def _extract_cells(self) -> List[dict]:
        """Extract all cells from notebook.

        Returns:
            List of cell dictionaries with metadata
        """
        cells = []
        for idx, cell in enumerate(self.notebook.cells):
            cells.append({
                'index': idx,
                'type': cell.cell_type,
                'source': cell.source,
                'metadata': cell.metadata
            })
        return cells

    def get_code_cells(self) -> List[str]:
        """Get source code from all code cells.

        Returns:
            List of source code strings from code cells
        """
        return [
            cell['source']
            for cell in self.cells
            if cell['type'] == 'code'
        ]

    def extract_imports(self) -> Set[str]:
        """Extract all imported packages from notebook code.

        Returns:
            Set of package names imported in the notebook
        """
        imports = set()

        for code in self.get_code_cells():
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # Get base package name (e.g., 'pandas' from 'pandas.core')
                            package = alias.name.split('.')[0]
                            imports.add(package)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            package = node.module.split('.')[0]
                            imports.add(package)
            except SyntaxError:
                # Skip cells with invalid syntax
                continue

        return imports

    def build_dependency_graph(self) -> Dict[int, Dict]:
        """Build dependency graph showing which cells depend on others.

        Returns:
            Dictionary mapping cell index to dependency info:
            {
                0: {'defines': {'x', 'y'}, 'uses': set(), 'depends_on': []},
                1: {'defines': {'z'}, 'uses': {'x'}, 'depends_on': [0]},
            }
        """
        graph = {}
        cell_vars = {}  # Track what variables each cell defines

        code_cells = self.get_code_cells()

        # First pass: identify what each cell defines
        for idx, code in enumerate(code_cells):
            defined = extract_defined_vars(code)
            used = extract_used_vars(code)

            cell_vars[idx] = defined
            graph[idx] = {
                'defines': defined,
                'uses': used,
                'depends_on': []
            }

        # Second pass: build dependencies
        for idx, info in graph.items():
            for var in info['uses']:
                # Find which earlier cell defined this variable
                for earlier_idx in range(idx):
                    if var in cell_vars.get(earlier_idx, set()):
                        if earlier_idx not in info['depends_on']:
                            info['depends_on'].append(earlier_idx)

        return graph
