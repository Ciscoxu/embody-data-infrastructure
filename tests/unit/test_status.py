from embody_data.status import OperationStatus, RunState


def test_status_lifecycle():
    status = OperationStatus.started("inspect")
    assert status.state is RunState.RUNNING
    status.finish(succeeded=True)
    assert status.state is RunState.SUCCEEDED
    assert status.finished_at is not None
