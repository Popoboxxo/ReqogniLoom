from django.test import Client


def test_get_mcp_with_event_stream_accept_returns_405():
    client = Client()
    resp = client.get("/mcp/", HTTP_ACCEPT="text/event-stream")
    assert resp.status_code == 405


def test_get_mcp_without_event_stream_accept_still_returns_info_json():
    client = Client()
    resp = client.get("/mcp/")
    assert resp.status_code == 200
    assert resp.json()["server"] == "ReqogniLoom MCP Server"
