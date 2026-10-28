import pytest

from fundlex.model import ModelError
from fundlex.guide_generation.model_router import GuideModelRouter
from fundlex.guide_generation.pipeline import GuidePipeline


class UnavailableGateway:
    model = 'test'
    provider = 'test'
    request_options = {}

    def __init__(self):
        self.calls = 0

    def call(self, **kwargs):
        self.calls += 1
        raise ModelError('MODEL_HTTP_ERROR')


def test_transport_failure_blocks_further_calls_and_cannot_complete_stage():
    gateway = UnavailableGateway()
    router = GuideModelRouter({'primary': gateway})
    arguments = dict(task_type='guide_req_extract', bounded_context='public regulation',
                     response_schema={'type': 'object'}, instruction='test')
    for _ in range(3):
        with pytest.raises(ModelError, match='MODEL_HTTP_ERROR'):
            router.call(**arguments)
    assert gateway.calls == 1
    assert len(router.records) == 1

    class Store:
        outcomes = []
        def get_completed_step(self, *args): return None
        def start_step(self, *args, **kwargs): return 1
        def finish_step(self, *args, **kwargs): self.outcomes.append(kwargs['status'])

    pipeline = object.__new__(GuidePipeline)
    pipeline.router = router
    pipeline.store = Store()
    pipeline.run_id = 'run'
    pipeline.payload = {}
    pipeline._update = lambda **kwargs: None
    with pytest.raises(ModelError, match='MODEL_HTTP_ERROR'):
        pipeline._stage('EXTRACT_REQUIREMENTS', 'input', lambda: {'requirements': []})
    assert pipeline.store.outcomes == ['failed']
