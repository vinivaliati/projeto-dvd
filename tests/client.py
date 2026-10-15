"""Test clients on http://localhost, a host the app trusts."""

from fastapi import FastAPI
from fastapi.testclient import TestClient


def client_for(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="http://localhost")
