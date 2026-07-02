import time
from typing import Optional

import requests


class OSSVerify:
    def __init__(self, base_url: str = "http://localhost:8000/api/v1"):
        self.base_url = base_url

    def analyzeDeveloper(
        self,
        github_username: str,
        github_token: Optional[str] = None,
        poll_interval: float = 3.0,
        timeout: float = 300.0,
    ) -> dict:
        r = requests.post(
            f"{self.base_url}/analyze",
            json={"github_username": github_username, "github_token": github_token},
        )
        r.raise_for_status()
        job = r.json()["data"]
        job_id = job["job_id"]

        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{self.base_url}/analyze/status/{job_id}")
            r.raise_for_status()
            status_data = r.json()["data"]
            if status_data["status"] == "complete":
                return status_data["data"]
            if status_data["status"] == "failed":
                raise RuntimeError(f"분석 실패: {status_data['error']}")
            time.sleep(poll_interval)

        raise TimeoutError(f"{timeout}초 내에 분석이 완료되지 않았습니다.")

    def getProfessionalProfile(self, github_username: str) -> dict:
        r = requests.get(f"{self.base_url}/profile/{github_username}")
        r.raise_for_status()
        return r.json()["data"]

    def issueCredential(self, github_username: str) -> dict:
        r = requests.post(
            f"{self.base_url}/credential/issue",
            json={"github_username": github_username},
        )
        r.raise_for_status()
        return r.json()["data"]

    def verifyCredential(self, credential_id: str) -> dict:
        r = requests.get(f"{self.base_url}/credential/verify/{credential_id}")
        r.raise_for_status()
        return r.json()["data"]
