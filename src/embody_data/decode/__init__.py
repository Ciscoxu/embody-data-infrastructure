"""Source-specific decoding plugins."""

from embody_data.decode.base import (
    AdapterKey,
    DecodeRequest,
    dispatch_decode,
    registered_adapter_keys,
    resolve_adapter,
)
from embody_data.decode.folder_bundle import FOLDER_BUNDLE_ADAPTER, FOLDER_BUNDLE_KEY
from embody_data.decode.genrobot import GENROBOT_MCAP_ADAPTER
from embody_data.decode.mcap import McapDecodedMessage, header_fields, iter_decoded

__all__ = [
    "GENROBOT_MCAP_ADAPTER",
    "FOLDER_BUNDLE_ADAPTER",
    "FOLDER_BUNDLE_KEY",
    "AdapterKey",
    "DecodeRequest",
    "McapDecodedMessage",
    "dispatch_decode",
    "header_fields",
    "iter_decoded",
    "registered_adapter_keys",
    "resolve_adapter",
]
