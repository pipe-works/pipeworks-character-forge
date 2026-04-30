"""Runtime configuration for the PipeWorks Character Forge service.

All settings can be overridden via environment variables (typically loaded
from ``/etc/pipeworks/character-forge/character-forge.env`` by the systemd
unit). Variable names use the ``PIPEWORKS_FORGE_`` prefix.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# Runtime mutable state lives outside the repo by default, mirroring the
# pipeworks-image-generator convention (PIPEWORKS_MODELS_DIR /
# PIPEWORKS_OUTPUTS_DIR pointed at /srv/work/pipeworks/runtime/...).
# Keeps multi-GB HF caches and per-run output dirs out of the working tree.
RUNTIME_ROOT = Path("/srv/work/pipeworks/runtime/character-forge")


class PipeworksForgeConfig(BaseSettings):
    """Pydantic-settings model holding all runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="PIPEWORKS_FORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_host: str = "127.0.0.1"
    server_port: int = 8410

    repo_root: Path = REPO_ROOT
    runs_dir: Path = RUNTIME_ROOT / "runs"
    models_dir: Path = RUNTIME_ROOT / "models"
    static_dir: Path = PACKAGE_ROOT / "static"
    templates_dir: Path = PACKAGE_ROOT / "templates"
    data_dir: Path = PACKAGE_ROOT / "data"

    flux2_model_id: str = "black-forest-labs/FLUX.2-klein-base-9B"
    device: str = "cuda"
    torch_dtype: str = "bfloat16"

    default_steps: int = 28
    default_guidance: float = 4.5

    enable_attention_slicing: bool = True
    # FLUX.2-klein-base-9B in bf16 (transformer + dual text encoders + VAE)
    # weighs in around 30 GiB resident on GPU, leaving no room for
    # activations on a 32 GiB card. CPU offload is required on the
    # canonical 5090 deployment; only flip this off on cards with
    # noticeably more VRAM (A100 80 GB, H100, etc.).
    enable_model_cpu_offload: bool = True

    disable_http_cache: bool = False

    log_level: str = Field(default="INFO")


config = PipeworksForgeConfig()
