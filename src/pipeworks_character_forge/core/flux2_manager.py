"""FLUX.2-klein-base-9B image-to-image lifecycle.

The manager holds a single ``AutoPipelineForImage2Image`` in VRAM for the
lifetime of the process. ``torch`` and ``diffusers`` are imported lazily
inside :meth:`Flux2KleinManager.load` so the rest of the app (and the
``[dev]`` test environment) can import this module without the optional
``[ml]`` extra installed.
"""

from __future__ import annotations

import gc
import logging
from typing import Any, Protocol

from PIL import Image

from pipeworks_character_forge.core.config import PipeworksForgeConfig

logger = logging.getLogger(__name__)


class I2IPipeline(Protocol):
    """Subset of the diffusers pipeline interface that the manager calls."""

    def __call__(self, **kwargs: Any) -> Any: ...


class Flux2KleinManager:
    """Lifecycle wrapper around the FLUX.2-klein image-to-image pipeline."""

    def __init__(self, config: PipeworksForgeConfig) -> None:
        self.config = config
        self.pipeline: I2IPipeline | None = None

    def load(self) -> None:
        """Instantiate the pipeline on the configured device. Idempotent."""
        if self.pipeline is not None:
            return

        # Lazy imports — the ``[ml]`` extra (torch + diffusers + accelerate +
        # transformers) is not required for the app to import. Installing
        # them is an operator step on the GPU host.
        import torch
        from diffusers import AutoPipelineForImage2Image

        dtype = getattr(torch, self.config.torch_dtype)
        logger.info(
            "Loading FLUX.2-klein image-to-image pipeline: %s "
            "(dtype=%s, device=%s, cpu_offload=%s)",
            self.config.flux2_model_id,
            self.config.torch_dtype,
            self.config.device,
            self.config.enable_model_cpu_offload,
        )

        self.config.models_dir.mkdir(parents=True, exist_ok=True)

        if self.config.enable_model_cpu_offload:
            # Load on CPU, then let accelerate stream modules to the GPU
            # on demand. Lower VRAM ceiling, higher per-step latency.
            pipeline = AutoPipelineForImage2Image.from_pretrained(
                self.config.flux2_model_id,
                torch_dtype=dtype,
                cache_dir=str(self.config.models_dir),
            )
            pipeline.enable_model_cpu_offload()
        else:
            # Place weights directly on the device via accelerate's
            # device_map. Avoids the transient CPU+GPU double-allocation
            # of ``pipeline.to(device)`` that OOMs the 5090 on the 9B
            # model even though the resident model fits.
            pipeline = AutoPipelineForImage2Image.from_pretrained(
                self.config.flux2_model_id,
                torch_dtype=dtype,
                cache_dir=str(self.config.models_dir),
                device_map=self.config.device,
            )

        if self.config.enable_attention_slicing:
            pipeline.enable_attention_slicing()

        self.pipeline = pipeline
        logger.info("FLUX.2-klein pipeline ready")

    def i2i(
        self,
        reference_image: Image.Image,
        prompt: str,
        *,
        steps: int,
        guidance: float,
        seed: int,
    ) -> Image.Image:
        """Run one reference-conditioned generation step.

        FLUX.2-klein's pipeline is conditioning-based, not denoising-strength
        based: the reference image steers character/style identity but the
        sampler always runs the full schedule. There is no ``strength``
        parameter in :class:`diffusers.Flux2KleinPipeline.__call__`.
        Loads the pipeline lazily on first call.
        """
        if self.pipeline is None:
            self.load()
        assert self.pipeline is not None

        import torch

        # When CPU offload is enabled the pipeline modules live on CPU until
        # accelerate moves them to GPU on demand; pinning the generator to a
        # specific device would mismatch that. Use a CPU generator in that
        # case — the pipeline reseeds the device-side noise from it.
        gen_device = "cpu" if self.config.enable_model_cpu_offload else self.config.device
        generator = torch.Generator(device=gen_device).manual_seed(seed)
        result = self.pipeline(
            prompt=prompt,
            image=reference_image,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=generator,
        )
        return result.images[0]  # type: ignore[no-any-return]

    def unload(self) -> None:
        """Drop the pipeline and free GPU memory. Safe to call multiple times."""
        if self.pipeline is None:
            return
        self.pipeline = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
