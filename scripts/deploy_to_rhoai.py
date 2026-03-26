#!/usr/bin/env python3
"""Deploy generated pipeline to RHOAI cluster."""

import os
import sys
from pathlib import Path
from typing import Optional

def deploy_pipeline(
    pipeline_yaml: Path,
    rhoai_endpoint: Optional[str] = None,
    auth_token: Optional[str] = None,
    experiment_name: str = "preflight_pipelines",
    run_name: Optional[str] = None
):
    """Deploy pipeline to RHOAI cluster.

    Args:
        pipeline_yaml: Path to compiled pipeline YAML
        rhoai_endpoint: RHOAI API endpoint (or set RHOAI_ENDPOINT env var)
        auth_token: Authentication token (or set RHOAI_TOKEN env var)
        experiment_name: Name of experiment to create/use
        run_name: Optional name for the pipeline run

    Returns:
        Run ID if successful
    """
    try:
        from kfp import Client
    except ImportError:
        print("❌ kfp not installed. Install with: pip install kfp")
        sys.exit(1)

    # Get connection details from args or environment
    endpoint = rhoai_endpoint or os.getenv('RHOAI_ENDPOINT')
    token = auth_token or os.getenv('RHOAI_TOKEN')

    if not endpoint:
        print("❌ RHOAI endpoint not provided.")
        print("   Set RHOAI_ENDPOINT environment variable or pass --endpoint")
        print("\n   Example: export RHOAI_ENDPOINT='https://ds-pipeline-dspa.apps.cluster.com'")
        sys.exit(1)

    if not token:
        print("❌ Authentication token not provided.")
        print("   Set RHOAI_TOKEN environment variable or pass --token")
        print("\n   Get token with: oc whoami -t")
        sys.exit(1)

    print(f"🔗 Connecting to RHOAI: {endpoint}")

    # Connect to RHOAI
    try:
        client = Client(
            host=endpoint,
            existing_token=token
        )
        print("✓ Connected successfully")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    # Upload pipeline
    pipeline_name = pipeline_yaml.stem
    print(f"\n📤 Uploading pipeline: {pipeline_name}")

    try:
        pipeline = client.upload_pipeline(
            pipeline_package_path=str(pipeline_yaml),
            pipeline_name=pipeline_name
        )
        print(f"✓ Pipeline uploaded: {pipeline.pipeline_id}")
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        sys.exit(1)

    # Create experiment
    print(f"\n🧪 Creating/getting experiment: {experiment_name}")

    try:
        experiment = client.create_experiment(experiment_name)
        print(f"✓ Experiment ready: {experiment.experiment_id}")
    except Exception as e:
        # Experiment might already exist
        print(f"⚠️  Using existing experiment (or creation failed): {e}")
        experiment = None

    # Create run
    run_name = run_name or f"{pipeline_name}_run_1"
    print(f"\n▶️  Creating pipeline run: {run_name}")

    try:
        run_params = {
            'job_name': run_name,
            'pipeline_id': pipeline.pipeline_id
        }
        if experiment:
            run_params['experiment_id'] = experiment.experiment_id

        run = client.run_pipeline(**run_params)

        print(f"✓ Pipeline run created successfully!")
        print(f"\n📊 Run Details:")
        print(f"   ID: {run.run_id}")
        print(f"   URL: {run.run_url}")
        print(f"\n✅ Deployment complete!")

        return run.run_id

    except Exception as e:
        print(f"❌ Run creation failed: {e}")
        sys.exit(1)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Deploy generated pipeline to RHOAI cluster"
    )
    parser.add_argument(
        'pipeline_yaml',
        type=Path,
        help='Path to compiled pipeline YAML file'
    )
    parser.add_argument(
        '--endpoint',
        help='RHOAI API endpoint (or set RHOAI_ENDPOINT env var)'
    )
    parser.add_argument(
        '--token',
        help='Authentication token (or set RHOAI_TOKEN env var)'
    )
    parser.add_argument(
        '--experiment',
        default='preflight_pipelines',
        help='Experiment name (default: preflight_pipelines)'
    )
    parser.add_argument(
        '--run-name',
        help='Pipeline run name (default: auto-generated)'
    )

    args = parser.parse_args()

    if not args.pipeline_yaml.exists():
        print(f"❌ Pipeline YAML not found: {args.pipeline_yaml}")
        sys.exit(1)

    print("=" * 60)
    print("RHOAI Pipeline Deployment")
    print("=" * 60)

    deploy_pipeline(
        pipeline_yaml=args.pipeline_yaml,
        rhoai_endpoint=args.endpoint,
        auth_token=args.token,
        experiment_name=args.experiment,
        run_name=args.run_name
    )


if __name__ == '__main__':
    main()
