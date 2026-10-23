"""Swagger에서 Java 인증 API와 RAG API의 호출 서버·인증 방식을 구분한다."""
import pytest
from fastapi.openapi.models import OpenAPI
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_combined_openapi_is_valid(client):
    schema = client.get("/openapi.json").json()
    OpenAPI.model_validate(schema)
    assert [tag["name"] for tag in schema["tags"]] == ["Java 인증", "RAG 안내", "서비스 상태"]


@pytest.mark.parametrize("path, method", [
    ("/api/signup", "post"), ("/api/login", "post"),
    ("/api/auth/check", "get"), ("/api/logout", "post"),
])
def test_java_operations_use_java_server(client, path, method):
    operation = client.get("/openapi.json").json()["paths"][path][method]
    assert operation["tags"] == ["Java 인증"]
    assert operation["servers"][0]["url"] == "http://localhost:8080"
    # 명세의 외부 서버를 생략하고 RAG 서버로 보내면 Java API를 실행하지 않는다.
    assert client.request(method, path).status_code == 404


@pytest.mark.parametrize("path", ["/api/signup", "/api/login"])
def test_credentials_are_public_form_inputs(client, path):
    operation = client.get("/openapi.json").json()["paths"][path]["post"]
    assert operation["security"] == []
    form = operation["requestBody"]["content"]["application/x-www-form-urlencoded"]["schema"]
    assert set(form["required"]) == {"username", "password"}
    assert form["properties"]["password"]["format"] == "password"


def test_login_documents_copyable_token(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/login"]["post"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert {"accessToken", "tokenType", "expiresIn"} <= set(schema["required"])
    assert "accessToken" in operation["description"]


def test_signup_and_logout_request_json_results(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "application/json" in paths["/api/signup"]["post"]["responses"]["201"]["content"]
    logout = paths["/api/logout"]["post"]
    assert "application/json" in logout["responses"]["200"]["content"]
    assert "Authorize" in logout["description"]


def test_auth_check_uses_authorize_but_public_operations_do_not(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/api/auth/check"]["get"]["security"] == [{"BearerAuth": []}]
    for path in ("/api/signup", "/api/login", "/api/logout"):
        assert paths[path]["post"]["security"] == []


def test_rag_and_health_keep_their_current_server(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/rag-query"]["post"]["tags"] == ["RAG 안내"]
    assert paths["/health"]["get"]["tags"] == ["서비스 상태"]
    assert "servers" not in paths["/rag-query"]["post"]
    assert "servers" not in paths["/health"]["get"]


def test_swagger_enables_cross_origin_cookie_sessions(client):
    response = client.get("/docs")
    assert response.status_code == 200
    assert '"withCredentials": true' in response.text
