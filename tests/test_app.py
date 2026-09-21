from fastapi.testclient import TestClient
from google.genai import types
from app import app, TOOLS

def test_pages_and_missing_key(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/api/config').json()['configured'] is False
        with client.websocket_connect('/ws/call', headers={'origin':'http://testserver'}) as ws:
            assert ws.receive_json()['type']=='error'

def test_tool_schema():
    config=types.LiveConnectConfig(response_modalities=['AUDIO'],tools=[{'function_declarations':TOOLS}])
    assert len(config.tools[0].function_declarations)==4


def test_phone_transcript_does_not_inject_an_unfinished_turn(monkeypatch, tmp_path):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app as module
    from booking import BookingStore

    class Session:
        def __init__(self):
            self.send_client_content = AsyncMock()
            self.send_realtime_input = AsyncMock()
            self.sent_response = False

        async def receive(self):
            if not self.sent_response:
                self.sent_response = True
                yield types.LiveServerMessage(voice_activity=types.VoiceActivity(
                    voice_activity_type=types.VoiceActivityType.ACTIVITY_END))
                yield types.LiveServerMessage(server_content=types.LiveServerContent(
                    input_transcription=types.Transcription(text='01234567890')))
                yield types.LiveServerMessage(server_content=types.LiveServerContent(
                    model_turn=types.Content(role='model', parts=[
                        types.Part(inline_data=types.Blob(
                            data=b'\x00\x00', mime_type='audio/pcm;rate=24000'))]),
                    turn_complete=True))
            await asyncio.Event().wait()

    session = Session()
    configs = []

    @asynccontextmanager
    async def connect(**kwargs):
        configs.append(types.LiveConnectConfig(**kwargs['config']))
        yield session

    close = AsyncMock()
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setattr(module, 'store', BookingStore(tmp_path / 'test.sqlite3'))
    monkeypatch.setattr(module.genai, 'Client', lambda **kwargs: SimpleNamespace(
        aio=SimpleNamespace(live=SimpleNamespace(connect=connect), aclose=close)))
    with TestClient(app) as client:
        with client.websocket_connect('/ws/call', headers={'origin': 'http://testserver'}) as ws:
            assert ws.receive_json()['type'] == 'ready'
            assert ws.receive_json()['type'] == 'thinking'
            assert ws.receive_json()['type'] == 'transcript'
            assert ws.receive_bytes() == b'\x00\x00'
            assert ws.receive_json()['type'] == 'turn_complete'

    session.send_client_content.assert_not_called()
    session.send_realtime_input.assert_awaited_once()
    assert 'greeting' in session.send_realtime_input.call_args.kwargs['text']
    detection = configs[0].realtime_input_config.automatic_activity_detection
    assert detection.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_HIGH
