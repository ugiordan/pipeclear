"""Command-line interface for RHOAI Pipeline Preflight."""
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table

from src.analyzer import NotebookAnalyzer
from src.validators.resource import ResourceEstimator
from src.validators.dependency import DependencyValidator
from src.validators.security import SecurityScanner
from src.validators.image import ImageValidator
from src.reporter import IssueReporter
from src.generator import PipelineGenerator


app = typer.Typer(help="RHOAI Pipeline Preflight - Notebook-to-Pipeline Converter")
console = Console()


@app.command()
def analyze(
    notebook_path: Path = typer.Argument(..., help="Path to Jupyter notebook"),
    output: Path = typer.Option(None, "--output", "-o", help="Output path for generated pipeline"),
    show_comparison: bool = typer.Option(False, "--compare", help="Show before/after time comparison"),
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text, json"),
):
    """Analyze notebook and generate pre-flight report."""

    # Error handling
    if not notebook_path.exists():
        console.print(f"[red]Error: Notebook not found: {notebook_path}[/red]")
        raise typer.Exit(code=1)

    if not notebook_path.suffix == '.ipynb':
        console.print(f"[red]Error: File must be a Jupyter notebook (.ipynb): {notebook_path}[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Analyzing notebook:[/bold] {notebook_path}\n")

    # Load and analyze notebook
    try:
        analyzer = NotebookAnalyzer(notebook_path)
    except Exception as e:
        console.print(f"[red]Error loading notebook: {e}[/red]")
        raise typer.Exit(code=1)

    # Run validators with progress
    from rich.progress import Progress, SpinnerColumn, TextColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Running pre-flight validators...", total=4)

        progress.update(task, description="🔍 Scanning for security issues...")
        security_scanner = SecurityScanner()
        security_report = security_scanner.analyze(analyzer)
        progress.advance(task)

        progress.update(task, description="💾 Estimating resource requirements...")
        resource_validator = ResourceEstimator()
        resource_report = resource_validator.analyze(analyzer)
        progress.advance(task)

        progress.update(task, description="📦 Validating dependencies...")
        dependency_validator = DependencyValidator()
        dependency_report = dependency_validator.analyze(analyzer)
        progress.advance(task)

        progress.update(task, description="🐳 Checking base image accessibility...")
        image_validator = ImageValidator()
        base_image = "registry.access.redhat.com/ubi9/python-311:latest"
        image_issues = image_validator.validate_image(base_image)
        progress.advance(task)

    # Generate report
    reporter = IssueReporter()
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
        'image': image_issues,
    })

    if output_format == "json":
        import json
        console.print(json.dumps(report, indent=2))
        if report['summary']['critical'] > 0:
            raise typer.Exit(code=1)
        return

    # Display summary
    console.print("\n[bold]Pre-Flight Analysis Summary[/bold]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Severity", style="dim")
    table.add_column("Count", justify="right")

    table.add_row("🚨 Critical", str(report['summary']['critical']))
    table.add_row("⚠️  Warning", str(report['summary']['warning']))
    table.add_row("✓ Total Issues", str(report['summary']['total']))

    console.print(table)

    # Show time savings
    if report['summary']['total'] > 0:
        time_saved = report['summary'].get('time_saved_human', 'Unknown')
        console.print(f"\n[bold green]⏱️  Estimated Time Saved: {time_saved}[/bold green]")

        if show_comparison:
            console.print("\n[bold]Before/After Comparison:[/bold]")
            console.print(f"  ❌ [red]Without Preflight:[/red] Pipeline would fail during execution")
            console.print(f"  ✅ [green]With Preflight:[/green] Issues caught in <5 seconds")
            console.print(f"  💰 [bold]Time Saved:[/bold] {time_saved}\n")

    # Display issues
    if report['issues']:
        console.print("\n[bold]Issues Found:[/bold]\n")

        for i, issue in enumerate(report['issues'], 1):
            severity_icon = "🚨" if issue['severity'] == 'critical' else "⚠️"
            console.print(f"{severity_icon} [{issue['category'].upper()}] {issue['message']}")

            # Show suggestion if available
            if 'suggestion' in issue:
                console.print(f"   {issue['suggestion']}")

            # Show time impact if available
            if 'time_impact' in issue:
                console.print(f"   ⏱️  Impact: {issue['time_impact']}")

            console.print()  # Blank line between issues
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
