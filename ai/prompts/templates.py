"""Prompt templates
================
A small, dependency-free templating helper for building prompts out of
named placeholders, used by ai/prompts/task_prompts.py and
ai/prompt_manager.py. Deliberately simpler than a full templating engine
(Jinja etc.) - Ultron's prompts are short and this keeps them readable as
plain Python string.format() templates with validation on top, rather
than pulling in a new dependency for something str.format() almost does
already.
"""

from dataclasses import dataclass
from string import Formatter
from typing import Dict, List, Optional

_formatter = Formatter()


def _extract_fields(template: str) -> List[str]:
    return [name for _, name, _, _ in _formatter.parse(template) if name]


@dataclass
class PromptTemplate:
    """A named, versioned prompt string with {placeholders}.

    Example:
        tpl = PromptTemplate(
            name="summarize",
            template="Summarize the following in {max_sentences} sentences:\\n\\n{text}",
        )
        tpl.render(text="...", max_sentences=2)
    """

    name: str
    template: str
    description: str = ""
    version: int = 1

    def __post_init__(self):
        self._fields = _extract_fields(self.template)

    @property
    def required_fields(self) -> List[str]:
        return list(self._fields)

    def render(self, **kwargs) -> str:
        """Fill in the template. Raises KeyError (with a clear message)
        if a required placeholder wasn't supplied, rather than silently
        sending a half-filled prompt to the model."""
        missing = [f for f in self._fields if f not in kwargs]
        if missing:
            raise KeyError(f"PromptTemplate '{self.name}' is missing value(s) for: {', '.join(missing)}")
        return self.template.format(**kwargs)


class TemplateRegistry:
    """Simple in-memory registry so callers can look templates up by name
    instead of importing each constant individually. Used by
    ai/prompt_manager.py to track and A/B-test prompt variants."""

    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        self._templates[template.name] = template

    def get(self, name: str) -> Optional[PromptTemplate]:
        return self._templates.get(name)

    def render(self, name: str, **kwargs) -> str:
        tpl = self.get(name)
        if tpl is None:
            raise KeyError(f"No prompt template registered under '{name}'")
        return tpl.render(**kwargs)

    def all_names(self) -> List[str]:
        return list(self._templates.keys())
