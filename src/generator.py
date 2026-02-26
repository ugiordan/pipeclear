"""KFP pipeline generation module."""
import re
from typing import List, Optional
from textwrap import dedent, indent


def sanitize_name(name: str) -> str:
    """Make a string a valid Python identifier."""
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if name and name[0].isdigit():
        name = 'pipeline_' + name
    return name


class PipelineGenerator:
    """Generates Kubeflow Pipeline code from notebook analysis."""

    def generate_component(
        self,
        name: str,
        code_cells: List[str],
        packages: Optional[List[str]] = None,
        base_image: str = "registry.access.redhat.com/ubi9/python-311:latest"
    ) -> str:
        """Generate KFP component from code cells.

        Args:
            name: Component function name
            code_cells: List of code cell contents
            packages: List of packages to install
            base_image: Container base image

        Returns:
            Component code as string
        """
        packages = packages or []

        # Combine all cell code
        combined_code = "\n".join(code_cells)

        # Indent the code for function body
        indented_code = indent(combined_code, "    ")

        # Build component
        safe_name = sanitize_name(name)
        component = f'''@dsl.component(
    base_image="{base_image}",
    packages_to_install={packages}
)
def {safe_name}():
    """Auto-generated component from notebook cells."""
{indented_code}
'''

        return component

    def generate_pipeline(
        self,
        analyzer,
        pipeline_name: str = "notebook_pipeline"
    ) -> str:
        """Generate complete KFP pipeline from notebook.

        Args:
            analyzer: NotebookAnalyzer instance
            pipeline_name: Name for the pipeline

        Returns:
            Complete pipeline Python code
        """
        # Get all imports from notebook
        imports = analyzer.extract_imports()
        packages = list(imports - {'os', 'sys', 'json'})  # Exclude stdlib

        # Get all code cells
        code_cells = analyzer.get_code_cells()

        # For MVP: create single component with all code
        component_code = self.generate_component(
            name="notebook_component",
            code_cells=code_cells,
            packages=packages
        )

        # Generate pipeline definition
        safe_pipeline_name = sanitize_name(pipeline_name)
        pipeline_def = f'''@dsl.pipeline(
    name="{pipeline_name}",
    description="Auto-generated from notebook"
)
def {safe_pipeline_name}():
    """Pipeline generated from Jupyter notebook."""
    task = notebook_component()
'''

        # Combine everything
        full_pipeline = f'''from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model

{component_code}

{pipeline_def}

if __name__ == '__main__':
    from kfp import compiler
    compiler.Compiler().compile(
        pipeline_func={safe_pipeline_name},
        package_path='{pipeline_name}.yaml'
    )
'''

        return dedent(full_pipeline)
