"""Jinja prompt loading helpers for RAG generation."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# StrictUndefined makes missing prompt variables fail fast during development
# instead of silently rendering incomplete prompts.
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(default_for_string=False, default=False),
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,
)


def render_prompt(template_name, **context):
    """Render a named prompt template with explicit context values."""
    template = env.get_template(template_name)
    return template.render(**context)
