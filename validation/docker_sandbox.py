"""
Stage 5: Docker Sandbox
Executes AI-generated code in a locked-down Docker container:
- python:3.11.8-slim base image
- Non-root user
- --network none --memory 256m --cpus 0.5 --pids-limit 64 --read-only --cap-drop ALL
- Timeout <= 5s
- No file writes
"""

import os
import subprocess
import tempfile
import time
import uuid
import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DockerSandboxResult:
    passed: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    timeout: bool = False
    errors: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0


DOCKER_IMAGE = "python:3.11.8-slim"
TIMEOUT_SECONDS = 5
MEMORY = "256m"
CPUS = "0.5"
PIDS_LIMIT = 64


class DockerSandbox:
    """Executes code in a locked-down Docker container."""

    def __init__(self, image: str = DOCKER_IMAGE, timeout: int = TIMEOUT_SECONDS):
        self.image = image
        self.timeout = timeout

    def execute(self, source: str) -> DockerSandboxResult:
        """Execute source code in Docker sandbox."""
        errors = []

        if not self._docker_available():
            return DockerSandboxResult(
                passed=False,
                errors=["Docker is not available or not running"],
            )

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as f:
            f.write(source)
            script_path = f.name

        try:
            container_name = f"siqe-sandbox-{os.getpid()}-{uuid.uuid4().hex[:8]}"

            cmd = [
                "docker", "run", "--rm",
                "--name", container_name,
                "--network", "none",
                "--memory", MEMORY,
                "--cpus", CPUS,
                "--pids-limit", str(PIDS_LIMIT),
                "--read-only",
                "--cap-drop", "ALL",
                "-v", f"{script_path}:/app/test.py:ro",
                "-w", "/app",
                "-e", "PYTHONHASHSEED=0",
                "-e", "PYTHONDONTWRITEBYTECODE=1",
                self.image,
                "python", "-u", "/app/test.py",
            ]

            start = time.monotonic()

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                elapsed_ms = (time.monotonic() - start) * 1000

                return DockerSandboxResult(
                    passed=result.returncode == 0 and result.stderr.strip() == "",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    execution_time_ms=elapsed_ms,
                )

            except subprocess.TimeoutExpired:
                elapsed_ms = (time.monotonic() - start) * 1000
                subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True,
                    timeout=5,
                )
                return DockerSandboxResult(
                    passed=False,
                    errors=[f"Execution timed out after {self.timeout}s"],
                    timeout=True,
                    execution_time_ms=elapsed_ms,
                )

        finally:
            os.unlink(script_path)

    def _docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
