"""Local demo-platform orchestration without cloud or web-framework coupling."""

from embody_data.platform.service import PlatformService
from embody_data.platform.sources import registered_source_adapters

__all__ = ["PlatformService", "registered_source_adapters"]
