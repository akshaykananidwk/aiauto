"""AIAuto API client — Python example (no dependencies beyond requests).

    pip install requests
    python aiauto_client.py
"""
import time

import requests

BASE = "https://your-server/api/public/v1"
KEY = "ak_your_api_key_here"
HEADERS = {"X-API-Key": KEY}


def submit_text(prompt: str) -> dict:
    r = requests.post(f"{BASE}/text", headers=HEADERS, json={"prompt": prompt})
    r.raise_for_status()
    return r.json()


def submit_image(prompt: str) -> dict:
    r = requests.post(f"{BASE}/images", headers=HEADERS, json={"prompt": prompt})
    r.raise_for_status()
    return r.json()


def submit_with_file(prompt: str, path: str) -> dict:
    with open(path, "rb") as fh:
        r = requests.post(f"{BASE}/jobs", headers=HEADERS,
                          data={"prompt": prompt, "type": "text"},
                          files={"files": fh})
    r.raise_for_status()
    return r.json()


def wait_for(job_id: str, timeout: int = 600) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = requests.get(f"{BASE}/jobs/{job_id}", headers=HEADERS).json()
        if job["status"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(3)
    raise TimeoutError(job_id)


def download(file_id: int, dest: str) -> None:
    r = requests.get(f"{BASE}/files/{file_id}", headers=HEADERS)
    r.raise_for_status()
    with open(dest, "wb") as fh:
        fh.write(r.content)


if __name__ == "__main__":
    job = submit_image("A watercolor painting of a lighthouse at dawn")
    print("submitted:", job["id"], "queue position:", job["queue_position"])
    job = wait_for(job["id"])
    print("status:", job["status"])
    if job["status"] == "completed":
        print(job["response"])
        for f in job["files"]:
            download(f["id"], f["name"])
            print("saved", f["name"])
    else:
        print("error:", job["error"])
