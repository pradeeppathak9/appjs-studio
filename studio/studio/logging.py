import logging
import re

_PROMPT = re.compile(r"(\"?(?:prompt|negative_prompt)\"?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)", re.I)


class PromptRedactingFilter(logging.Filter):
    """Blank out prompt values in log lines unless LOG_PROMPTS is on."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "prompt" in message.lower():
            record.msg = _PROMPT.sub(r"\1<redacted>", message)
            record.args = ()
        return True


def configure_logging(level: str = "INFO", log_prompts: bool = False) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    if not log_prompts:
        handler.addFilter(PromptRedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
