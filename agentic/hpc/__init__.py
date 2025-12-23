"""HPC helpers (placeholder)"""

__all__ = ["slurm_template_path"]

import os

slurm_template_path = os.path.join(os.path.dirname(__file__), "slurm_template.sh")
