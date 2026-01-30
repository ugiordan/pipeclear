"""Resource estimation validator."""
import re
from typing import List, Dict, Optional


# Known model sizes (in billions of parameters)
MODEL_PARAMS = {
    'llama-2-7b': 7,
    'llama-2-13b': 13,
    'llama-2-70b': 70,
    'llama-3.1-8b': 8,
    'qwen2.5-7b': 7,
    'mistral-7b': 7,
}


class ResourceEstimator:
    """Estimates compute resource requirements from notebook code."""

    def detect_models(self, code: str) -> List[Dict]:
        """Detect model loading patterns in code.

        Args:
            code: Python source code

        Returns:
            List of detected models with metadata
        """
        models = []

        # Pattern: AutoModelForCausalLM.from_pretrained('model-name')
        hf_pattern = r"from_pretrained\(['\"]([^'\"]+)['\"]\)"

        for match in re.finditer(hf_pattern, code):
            model_name = match.group(1)
            models.append({
                'name': model_name,
                'type': 'huggingface',
                'source': match.group(0)
            })

        return models

    def estimate_memory(
        self,
        model_name: str,
        precision: str = 'fp16',
        training: bool = False
    ) -> float:
        """Estimate memory requirements for a model.

        Args:
            model_name: Model identifier (e.g., 'meta-llama/Llama-2-7b')
            precision: Model precision ('fp32', 'fp16', 'int8')
            training: Whether model will be used for training (vs inference)

        Returns:
            Estimated memory in GB
        """
        # Normalize model name to lookup key
        model_key = model_name.lower().split('/')[-1]

        # Find matching model size
        params_b = None
        for key, params in MODEL_PARAMS.items():
            if key in model_key:
                params_b = params
                break

        if params_b is None:
            # Unknown model, return conservative estimate
            return 32.0

        # Bytes per parameter based on precision
        bytes_per_param = {
            'fp32': 4,
            'fp16': 2,
            'int8': 1,
        }.get(precision, 2)

        # Base memory: params * bytes
        base_memory_gb = (params_b * 1e9 * bytes_per_param) / (1024**3)

        # Add overhead
        if training:
            # Training needs gradients + optimizer states
            memory_gb = base_memory_gb * 2.5
        else:
            # Inference overhead for activations
            memory_gb = base_memory_gb * 1.5

        return round(memory_gb, 1)

    def analyze(self, analyzer) -> Dict:
        """Analyze notebook for resource requirements.

        Args:
            analyzer: NotebookAnalyzer instance

        Returns:
            Resource estimation report
        """
        report = {
            'gpu_required': False,
            'estimated_vram_gb': 0,
            'estimated_cpu_cores': 2,
            'estimated_memory_gb': 8,
            'models': []
        }

        # Check all code cells for model loading
        for code in analyzer.get_code_cells():
            models = self.detect_models(code)

            for model in models:
                memory = self.estimate_memory(model['name'])
                model['estimated_vram_gb'] = memory
                report['models'].append(model)

                if memory > 0:
                    report['gpu_required'] = True
                    report['estimated_vram_gb'] = max(
                        report['estimated_vram_gb'],
                        memory
                    )

        return report
