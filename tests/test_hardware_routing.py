"""Fit-to-hardware routing: make min_ram_gb actually drive model selection.

Encodes the "edge orchestrator" story — a capable local box runs a fitting local
model for free-tier work; a Raspberry Pi (RAM budget 0) delegates to the cloud.
Plus a slim-install guard: the local research path must import without the
`mantis` extra (langchain_openai).
"""

from __future__ import annotations

import subprocess
import sys

from silkroute.agent.router import (
    PROFILE_RAM_GB,
    best_local_model,
    model_fits_ram,
    select_model,
)
from silkroute.config.settings import HardwareProfile, ModelTier
from silkroute.providers.models import Provider, get_model


class TestModelFitsRam:
    def test_local_model_fits_when_ram_sufficient(self) -> None:
        m = get_model("ollama/qwen2.5:7b")  # min_ram_gb = 8
        assert m is not None
        assert model_fits_ram(m, 8.0) is True
        assert model_fits_ram(m, 16.0) is True

    def test_local_model_does_not_fit_when_ram_short(self) -> None:
        m = get_model("ollama/qwen2.5:14b")  # min_ram_gb = 16
        assert m is not None
        assert model_fits_ram(m, 8.0) is False

    def test_cloud_model_never_fits_local(self) -> None:
        m = get_model("deepseek/deepseek-v3.2")  # cloud, min_ram_gb = 0
        assert m is not None
        assert model_fits_ram(m, 999.0) is False


class TestBestLocalModel:
    def test_none_when_no_budget(self) -> None:
        assert best_local_model(0.0) is None
        assert best_local_model(4.0) is None  # smallest local model needs 8 GB

    def test_picks_biggest_fitting_model(self) -> None:
        assert best_local_model(8.0).min_ram_gb == 8.0  # type: ignore[union-attr]
        assert best_local_model(16.0).min_ram_gb == 16.0  # type: ignore[union-attr]
        assert best_local_model(64.0).min_ram_gb == 24.0  # type: ignore[union-attr]

    def test_result_is_local(self) -> None:
        m = best_local_model(24.0)
        assert m is not None and m.provider == Provider.OLLAMA


class TestProfileRamMap:
    def test_pi_and_vps_delegate(self) -> None:
        assert PROFILE_RAM_GB[HardwareProfile.RASPBERRY_PI] == 0.0
        assert PROFILE_RAM_GB[HardwareProfile.HETZNER_VPS] == 0.0

    def test_workstations_have_budget(self) -> None:
        assert PROFILE_RAM_GB[HardwareProfile.MAC_STUDIO] >= 24.0


class TestSelectModelHardware:
    def test_pi_delegates_to_cloud(self) -> None:
        m = select_model(ModelTier.FREE, hardware_profile=HardwareProfile.RASPBERRY_PI)
        assert m.provider != Provider.OLLAMA  # Pi runs orchestrator, not inference

    def test_capable_box_runs_local(self) -> None:
        m = select_model(ModelTier.FREE, hardware_profile=HardwareProfile.MAC_STUDIO)
        assert m.provider == Provider.OLLAMA

    def test_non_free_tier_stays_cloud_even_on_big_box(self) -> None:
        m = select_model(ModelTier.STANDARD, hardware_profile=HardwareProfile.MAC_STUDIO)
        assert m.provider != Provider.OLLAMA

    def test_no_profile_unchanged(self) -> None:
        m = select_model(ModelTier.FREE, hardware_profile=None)
        assert m.provider != Provider.OLLAMA  # existing behavior: cloud

    def test_user_override_beats_hardware(self) -> None:
        m = select_model(
            ModelTier.FREE,
            preferred_model="deepseek/deepseek-v3.2",
            hardware_profile=HardwareProfile.MAC_STUDIO,
        )
        assert m.model_id == "deepseek/deepseek-v3.2"


class TestSlimInstall:
    def test_autoresearch_llm_imports_without_langchain_openai(self) -> None:
        """The local research path must not require the mantis extra to import."""
        code = (
            "import sys\n"
            "sys.modules['langchain_openai'] = None\n"  # any import → ImportError
            "import silkroute.autoresearch.llm\n"
            "print('IMPORT_OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "IMPORT_OK" in result.stdout
