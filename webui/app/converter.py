import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from markitdown import MarkItDown

logger = logging.getLogger("markitdown-webui")

MAX_UPLOAD_MB = float(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = int(MAX_UPLOAD_MB * 1024 * 1024)


def _build_markitdown() -> MarkItDown:
    kwargs = {}

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        try:
            from openai import OpenAI

            kwargs["llm_client"] = OpenAI(api_key=openai_api_key)
            kwargs["llm_model"] = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            logger.info("LLM image captioning enabled (model=%s)", kwargs["llm_model"])
        except Exception:
            logger.exception("Failed to initialize OpenAI client; captioning disabled")

    docintel_endpoint = os.environ.get("AZURE_DOC_INTEL_ENDPOINT")
    if docintel_endpoint:
        kwargs["docintel_endpoint"] = docintel_endpoint
        logger.info("Azure Document Intelligence enabled (endpoint=%s)", docintel_endpoint)

    return MarkItDown(**kwargs)


_markitdown: Optional[MarkItDown] = None


def get_markitdown() -> MarkItDown:
    global _markitdown
    if _markitdown is None:
        _markitdown = _build_markitdown()
    return _markitdown


@dataclass
class ConversionResult:
    name: str
    markdown: Optional[str] = None
    error: Optional[str] = None


def convert_bytes(name: str, data: bytes) -> ConversionResult:
    if len(data) > MAX_UPLOAD_BYTES:
        return ConversionResult(
            name=name,
            error=f"File exceeds the {MAX_UPLOAD_MB:g} MB upload limit.",
        )

    suffix = Path(name).suffix
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        result = get_markitdown().convert(tmp_path)
        return ConversionResult(name=name, markdown=result.text_content)
    except Exception as exc:  # noqa: BLE001 - surface conversion errors to the user
        logger.warning("Conversion failed for %s: %s", name, exc)
        return ConversionResult(name=name, error=str(exc))
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def convert_url(url: str) -> ConversionResult:
    try:
        result = get_markitdown().convert(url)
        return ConversionResult(name=url, markdown=result.text_content)
    except Exception as exc:  # noqa: BLE001 - surface conversion errors to the user
        logger.warning("Conversion failed for %s: %s", url, exc)
        return ConversionResult(name=url, error=str(exc))
