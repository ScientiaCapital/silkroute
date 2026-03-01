"""LLM-native skills: code_review and summarize.

Both skills use SkillContext.get_llm() to obtain a ChatOpenAI client
and invoke it with structured prompts.
"""

from __future__ import annotations

import structlog

from silkroute.mantis.skills.models import SkillCategory, SkillContext, SkillSpec

log = structlog.get_logger()

_CODE_REVIEW_MODEL = "deepseek/deepseek-r1-0528:free"
_SUMMARIZE_MODEL = "deepseek/deepseek-chat:free"

_CODE_REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the provided code for:
1. Correctness and logic errors
2. Security vulnerabilities (injection, auth, secrets exposure)
3. Performance issues and anti-patterns
4. Maintainability and readability
5. Missing error handling

Provide actionable, concise feedback. Format as a bulleted list of findings.
Focus on what matters most for production quality."""

_SUMMARIZE_SYSTEM_PROMPT = """You are a precise summarizer. Condense the provided text into a clear,
accurate summary that captures the key points. Be concise and factual.
Do not add information not present in the source text."""


async def _code_review_handler(
    code: str,
    context: str = "",
    focus: str = "",
    _skill_ctx: SkillContext | None = None,
) -> str:
    """Review code using a DeepSeek reasoning model."""
    if _skill_ctx is None:
        return "Error: SkillContext is required for LLM-native skills"

    llm = _skill_ctx.get_llm(_CODE_REVIEW_MODEL)

    user_content = f"Code to review:\n\n```\n{code}\n```"
    if context:
        user_content = f"Context: {context}\n\n{user_content}"
    if focus:
        user_content += f"\n\nFocus particularly on: {focus}"

    try:
        # LangChain ChatOpenAI interface
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_CODE_REVIEW_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await llm.ainvoke(messages)
        return str(response.content)
    except Exception as e:
        log.error("code_review_llm_error", error=str(e))
        return f"Error during code review: {e}"


async def _summarize_handler(
    text: str,
    max_length: int = 200,
    _skill_ctx: SkillContext | None = None,
) -> str:
    """Summarize text using a free-tier model."""
    if _skill_ctx is None:
        return "Error: SkillContext is required for LLM-native skills"

    llm = _skill_ctx.get_llm(_SUMMARIZE_MODEL)
    max_length = min(max(max_length, 50), 2000)

    user_content = (
        f"Summarize the following text in at most {max_length} words:\n\n{text}"
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=_SUMMARIZE_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await llm.ainvoke(messages)
        return str(response.content)
    except Exception as e:
        log.error("summarize_llm_error", error=str(e))
        return f"Error during summarization: {e}"


code_review_skill = SkillSpec(
    name="code_review",
    description=(
        "Review code for correctness, security, performance, and maintainability. "
        "Uses DeepSeek reasoning model. Returns a bulleted list of findings."
    ),
    category=SkillCategory.LLM_NATIVE,
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The code to review",
            },
            "context": {
                "type": "string",
                "description": "Optional context about what the code does or its purpose",
                "default": "",
            },
            "focus": {
                "type": "string",
                "description": (
                    "Optional specific area to focus on (e.g. 'security', 'performance')"
                ),
                "default": "",
            },
        },
        "required": ["code"],
    },
    handler=_code_review_handler,
    is_llm_native=True,
    system_prompt=_CODE_REVIEW_SYSTEM_PROMPT,
    model_hint=_CODE_REVIEW_MODEL,
    max_budget_usd=0.10,
)

summarize_skill = SkillSpec(
    name="summarize",
    description=(
        "Summarize a block of text using a free-tier LLM. "
        "Useful for condensing long documents, logs, or research results."
    ),
    category=SkillCategory.LLM_NATIVE,
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to summarize",
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum summary length in words (50-2000, default: 200)",
                "default": 200,
            },
        },
        "required": ["text"],
    },
    handler=_summarize_handler,
    is_llm_native=True,
    system_prompt=_SUMMARIZE_SYSTEM_PROMPT,
    model_hint=_SUMMARIZE_MODEL,
    max_budget_usd=0.05,
)
