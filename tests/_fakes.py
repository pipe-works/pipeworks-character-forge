"""Test doubles for components that depend on heavy ML libraries."""

from __future__ import annotations

from PIL import Image

from pipeworks_character_forge.core.config import PipeworksForgeConfig
from pipeworks_character_forge.core.flux2_manager import Flux2KleinManager


class FakeFlux2KleinManager(Flux2KleinManager):
    """Manager that synthesizes solid-color PNGs instead of loading FLUX.2-klein.

    Lets us exercise the API surface (lifespan, routing, dependency wiring,
    multipart parsing, response encoding) without installing torch /
    diffusers or burning GPU minutes in CI.
    """

    def __init__(
        self, config: PipeworksForgeConfig, *, color: tuple[int, int, int] = (96, 128, 96)
    ):
        super().__init__(config)
        self._color = color
        self.calls: list[dict[str, object]] = []

    def load(self) -> None:
        self.pipeline = object()  # truthy sentinel; never actually invoked

    def i2i(
        self,
        reference_image: Image.Image,
        prompt: str,
        *,
        steps: int,
        guidance: float,
        seed: int,
    ) -> Image.Image:
        self.calls.append(
            {
                "prompt": prompt,
                "steps": steps,
                "guidance": guidance,
                "seed": seed,
                "ref_size": reference_image.size,
            }
        )
        return Image.new("RGB", reference_image.size, color=self._color)

    def unload(self) -> None:
        self.pipeline = None
