from embody_data.metadata.source_profiles import GENROBOT_REALOMIN
from embody_data.representation.genrobot import descriptor_for, profile_topic


def test_genrobot_semantics_are_human_observations():
    assert GENROBOT_REALOMIN.collection_mode == "human_wearable"
    pose = profile_topic("/robot1/vio/eef_pose")
    gripper = profile_topic("/robot0/sensor/magnetic_encoder")
    assert pose is not None and pose.semantic_role == "observed_device_pose"
    assert gripper is not None and gripper.unit == "meter"
    descriptor = descriptor_for("/robot0/vio/eef_pose")
    assert descriptor is not None
    assert descriptor.collection_mode == "human_wearable"
    assert descriptor.semantic_role == "observed_device_pose"
    assert descriptor.calibration_id == "not_applicable"
    assert descriptor.extensions["target_embodiment"] == "not_applicable"
