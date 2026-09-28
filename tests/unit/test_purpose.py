import pytest

from embody_data.errors import EmbodyDataError
from embody_data.purpose import PurposeKind, PurposeProfile, run_purpose


def test_profile_from_dict_preserves_explicit_purpose():
    profile = PurposeProfile.from_dict(
        {
            "name": "local_exploration",
            "purpose": "exploration",
            "version": "0.1.0",
            "options": {"preview_stride": 2},
        }
    )

    assert profile.purpose == PurposeKind.EXPLORATION
    assert profile.options["preview_stride"] == 2


@pytest.mark.parametrize(
    "kind",
    [
        PurposeKind.LEARNING_READINESS,
        PurposeKind.RETARGETING,
        PurposeKind.CONTROL_EVALUATION,
    ],
)
def test_unimplemented_purposes_are_explicit_interfaces(tmp_path, kind):
    profile = PurposeProfile(name=kind.value, purpose=kind, version="0.1.0")

    with pytest.raises(EmbodyDataError) as error:
        run_purpose(tmp_path / "processed", tmp_path / "purpose", profile)

    assert error.value.code == "purpose_unsupported"
    assert (
        "training, IK, retargeting, and control evaluation"
        in error.value.details["not_implemented"]
    )
