"""
Ollama lifecycle manager – auto‑start/stop for Schola‑Herv AI features.
"""

import subprocess
import time
import socket
import os
import signal
import logging
from typing import Optional

logger = logging.getLogger("schola_herv.ai.ollama_manager")

OLLAMA_PORT = 11434
OLLAMA_HOST = "127.0.0.1"
STARTUP_TIMEOUT = 30  # seconds to wait for Ollama to become ready

_ollama_process: Optional[subprocess.Popen] = None


def _is_port_open(host: str, port: int) -> bool:
    """Check if a port is open on localhost."""
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _ollama_binary_exists() -> bool:
    """Check if the 'ollama' command is available."""
    try:
        subprocess.run(["ollama", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def start_ollama() -> bool:
    """
    Attempt to start Ollama in the background.
    Returns True if Ollama is already running, or was started successfully.
    Returns False if Ollama cannot be started (e.g., not installed).
    """
    global _ollama_process

    if _is_port_open(OLLAMA_HOST, OLLAMA_PORT):
        logger.info("Ollama is already running.")
        return True

    if not _ollama_binary_exists():
        logger.warning("Ollama not found. Please install it: https://ollama.com/download")
        return False

    logger.info("Starting Ollama in the background...")
    try:
        _ollama_process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )
    except Exception as e:
        logger.warning(f"Failed to start Ollama: {e}")
        return False

    # Wait until the port is open or timeout
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if _is_port_open(OLLAMA_HOST, OLLAMA_PORT):
            logger.info("Ollama is now ready.")
            return True
        time.sleep(0.5)

    logger.warning("Ollama did not start within the timeout. AI features may not work.")
    return False


def stop_ollama():
    """Stop the Ollama server if we started it."""
    global _ollama_process
    if _ollama_process is not None:
        logger.info("Stopping Ollama (started by Schola‑Herv)...")
        try:
            if os.name == "nt":
                _ollama_process.terminate()
            else:
                os.killpg(os.getpgid(_ollama_process.pid), signal.SIGTERM)
        except Exception:
            pass
        _ollama_process = None


def ensure_ollama_running(ai_features_enabled: bool) -> bool:
    """
    If any AI feature is enabled, make sure Ollama is reachable.
    Returns True if Ollama is available, False otherwise.
    """
    if not ai_features_enabled:
        return False
    return start_ollama()