"""외부 모델 호출 없는 합성 내부 계약 검증. 작성자: 김진우."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from app.internal import app
from app.core.state import state


class InternalTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"INTERNAL_SERVICE_TOKEN": "synthetic-" * 8})
        self.env.start()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + "synthetic-" * 8}
        state.clear()

    def tearDown(self):
        state.clear()
        self.env.stop()

    def test_auth_and_demo_routes(self):
        self.assertEqual(401, self.client.post('/internal/chat/answer', json={"contractVersion": "1.0", "message": "안녕"}).status_code)
        for route in ('/chat', '/auth/login', '/conversations', '/docs', '/openapi.json'):
            self.assertEqual(404, self.client.get(route).status_code)

    def test_rejects_unknown_fields_blank_and_long_input_without_echo(self):
        for body in ({"message": " "}, {"message": "가" * 2001}, {"userId": "untrusted"}):
            data = {"contractVersion": "1.0", "message": "합성 질문", **body}
            response = self.client.post('/internal/chat/answer', json=data, headers=self.headers)
            self.assertEqual(422, response.status_code)
            self.assertEqual({"code": "INVALID_INPUT"}, response.json())

    def test_calls_existing_orchestrator_with_trusted_context(self):
        result = SimpleNamespace(grounded=False, answer="합성 답변", conversation_summary="요약", intent=SimpleNamespace(value="GENERAL"), emergency=False, personal_context_used=True)
        state['chat_orchestrator'] = Mock(answer=Mock(return_value=result))
        response = self.client.post('/internal/chat/answer', headers=self.headers,
                                    json={"contractVersion": "1.0", "message": "합성 질문", "personalContext": "합성 검진 문맥"})
        self.assertEqual(200, response.status_code)
        self.assertEqual("합성 답변", response.json()['answer'])
        loader = state['chat_orchestrator'].answer.call_args.kwargs['personal_context_loader']
        self.assertEqual("합성 검진 문맥", loader('question', []))

    def test_errors_do_not_echo_provider_secrets(self):
        state['chat_orchestrator'] = Mock(answer=Mock(side_effect=ValueError('secret-synthetic')))
        response = self.client.post('/internal/chat/answer', headers=self.headers, json={"contractVersion": "1.0", "message": "합성"})
        self.assertEqual(503, response.status_code)
        self.assertNotIn('secret-synthetic', response.text)

    def test_readiness_requires_orchestrator(self):
        self.assertEqual(503, self.client.get('/health/ready').status_code)
        state.update(ready=True, chat_orchestrator=Mock())
        self.assertEqual(200, self.client.get('/health/ready').status_code)

    def test_limits_total_bytes(self):
        response = self.client.post('/internal/chat/answer', headers=self.headers, content=b'x' * 262145)
        self.assertEqual(413, response.status_code)

    def test_stream_preserves_partial_tokens_before_sanitized_error(self):
        def events(*args, **kwargs):
            yield SimpleNamespace(event='token', text='합성 부분 답변')
            raise ValueError('synthetic-provider-secret')
        state['chat_orchestrator'] = SimpleNamespace(stream_answer=events)
        response = self.client.post('/internal/chat/stream', headers=self.headers,
                                    json={'contractVersion':'1.0','message':'합성 질문'})
        self.assertEqual(200, response.status_code)
        self.assertIn('합성 부분 답변', response.text)
        self.assertIn('event: error', response.text)
        self.assertNotIn('synthetic-provider-secret', response.text)


if __name__ == '__main__':
    unittest.main()
