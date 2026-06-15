"""Prompt templates for every stage of the research pipeline."""

from app.prompts.planner import PLANNER_PROMPT
from app.prompts.extractor import EXTRACTOR_PROMPT
from app.prompts.verifier import VERIFIER_PROMPT
from app.prompts.synthesizer import SYNTHESIZER_PROMPT
from app.prompts.reporter import REPORTER_PROMPT

__all__ = [
    "PLANNER_PROMPT",
    "EXTRACTOR_PROMPT",
    "VERIFIER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "REPORTER_PROMPT",
]
