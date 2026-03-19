"""PipeClear-enhanced KFP compiler with pre-flight validation."""
import sys
import yaml
from kfp import compiler


class PipeClearCompiler:
    """Wraps kfp.compiler.Compiler with PipeClear validation."""

    def __init__(self, fail_on_critical=True, allowed_registries=None):
        self._compiler = compiler.Compiler()
        self.fail_on_critical = fail_on_critical
        self.allowed_registries = allowed_registries

    def validate_pipeline_spec(self, spec: dict) -> dict:
        """Validate a compiled pipeline IR spec."""
        critical = []
        warnings = []

        deployment_spec = spec.get('deploymentSpec', {})
        executors = deployment_spec.get('executors', {})

        for executor_name, executor in executors.items():
            container = executor.get('container', {})
            image = container.get('image', '')

            if not image:
                critical.append({
                    'message': f'Executor {executor_name} has no container image',
                    'severity': 'critical',
                })
                continue

            tag = image.split(':')[-1] if ':' in image else 'latest'
            if tag == 'latest':
                warnings.append({
                    'message': f'Image {image} uses mutable "latest" tag',
                    'severity': 'warning',
                })

            if self.allowed_registries:
                registry = image.split('/')[0]
                if registry not in self.allowed_registries:
                    critical.append({
                        'message': f'Image {image} not from allowed registry. Allowed: {self.allowed_registries}',
                        'severity': 'critical',
                    })

        # Task count validation based on executors
        executor_count = len(executors)
        if executor_count > 100:
            critical.append({
                'message': f'Pipeline has {executor_count} tasks, exceeding maximum of 100',
                'severity': 'critical',
            })
        elif executor_count > 50:
            warnings.append({
                'message': f'Pipeline has {executor_count} tasks - consider splitting into smaller pipelines',
                'severity': 'warning',
            })

        # Root DAG task count validation
        root = spec.get('root', {})
        dag = root.get('dag', {})
        tasks = dag.get('tasks', {})
        task_count = len(tasks)
        if task_count > 100:
            critical.append({
                'message': f'Pipeline DAG has {task_count} tasks, exceeding maximum of 100',
                'severity': 'critical',
            })

        return {'critical': critical, 'warnings': warnings}

    def compile(self, pipeline_func, package_path, **kwargs):
        """Compile pipeline with PipeClear pre-flight validation."""
        self._compiler.compile(
            pipeline_func=pipeline_func,
            package_path=package_path,
            **kwargs,
        )

        with open(package_path, 'r') as f:
            spec = yaml.safe_load(f)

        result = self.validate_pipeline_spec(spec)

        for w in result['warnings']:
            print(f"PipeClear WARNING: {w['message']}", file=sys.stderr)

        if self.fail_on_critical and result['critical']:
            for c in result['critical']:
                print(f"PipeClear CRITICAL: {c['message']}", file=sys.stderr)
            import os
            os.remove(package_path)
            raise SystemExit(
                f"PipeClear blocked compilation: {len(result['critical'])} critical issue(s) found"
            )

        return result
