from typing import Optional

import requests


class OSSVerify:
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url

    def analyzeDeveloper(self, github_username: str, github_token: Optional[str] = None) -> dict:
        response = requests.post(
            f"{self.base_url}/analyze",
            json={"github_username": github_username, "github_token": github_token},
        )
        return response.json()["data"]

    def getProfessionalProfile(self, github_username: str) -> dict:
        response = requests.get(f"{self.base_url}/profile/{github_username}")
        return response.json()["data"]

    def issueCredential(self, github_username: str) -> dict:
        response = requests.post(
            f"{self.base_url}/credential/issue",
            json={"github_username": github_username},
        )
        return response.json()["data"]

    def verifyCredential(self, credential_id: str) -> dict:
        response = requests.get(f"{self.base_url}/credential/verify/{credential_id}")
        return response.json()["data"]
