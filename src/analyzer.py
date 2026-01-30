"""Notebook analysis and parsing module."""
from pathlib import Path
from typing import List
import nbformat
from nbformat.notebooknode import NotebookNode


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
