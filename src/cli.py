"""Command-line interface for RHOAI Pipeline Preflight."""
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table

from src.analyzer import NotebookAnalyzer
from src.validators.resource import ResourceEstimator
from src.validators.dependency import DependencyValidator
from src.validators.security import SecurityScanner
from src.reporter import IssueReporter
from src.generator import PipelineGenerator


app = typer.Typer(help="RHOAI Pipeline Preflight - Notebook-to-Pipeline Converter")
console = Console()


@app.command()
def analyze(
    notebook_path: Path = typer.Argument(..., help="Path to Jupyter notebook"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path for generated pipeline"),
):
    """Analyze notebook and generate pre-flight report."""

    console.print(f"\n[bold]Analyzing notebook:[/bold] {notebook_path}\n")

    # Load and analyze notebook
    analyzer = NotebookAnalyzer(notebook_path)

    # Run validators
    console.print("[yellow]Running pre-flight validators...[/yellow]")

    resource_validator = ResourceEstimator()
    resource_report = resource_validator.analyze(analyzer)

    dependency_validator = DependencyValidator()
    dependency_report = dependency_validator.analyze(analyzer)

    security_scanner = SecurityScanner()
    security_report = security_scanner.analyze(analyzer)

    # Generate report
    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    })

    # Display summary
    console.print("\n[bold]Pre-Flight Analysis Summary[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Severity", style="dim")
    table.add_column("Count", justify="right")

    table.add_row("🚨 Critical", str(report['summary']['critical']))
    table.add_row("⚠️  Warning", str(report['summary']['warning']))
    table.add_row("✓ Total Issues", str(report['summary']['total']))

    console.print(table)

    # Display issues
    if report['issues']:
        console.print("\n[bold]Issues Found:[/bold]\n")

        for issue in report['issues']:
            severity_icon = "🚨" if issue['severity'] == 'critical' else "⚠️"
            console.print(f"{severity_icon} [{issue['category'].upper()}] {issue['message']}\n")
    else:
        console.print("\n[green]✓ No issues found! Notebook looks good.[/green]\n")

    # Generate pipeline if requested
    if output:
        console.print(f"[yellow]Generating pipeline...[/yellow]")

        generator = PipelineGenerator()
        pipeline_code = generator.generate_pipeline(
            analyzer=analyzer,
            pipeline_name=notebook_path.stem
        )

        output.write_text(pipeline_code)
        console.print(f"[green]✓ Pipeline generated:[/green] {output}\n")

    # Exit with error code if critical issues found
    if report['summary']['critical'] > 0:
        console.print("[red]Critical issues detected. Fix before deploying.[/red]")
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show version information."""
    console.print("[bold]RHOAI Pipeline Preflight[/bold] v0.1.0")


if __name__ == "__main__":
    app()
