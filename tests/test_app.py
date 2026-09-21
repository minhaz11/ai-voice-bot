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
