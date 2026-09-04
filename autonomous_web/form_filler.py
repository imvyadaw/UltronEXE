"""
form_filler.py
===============
Fills and submits web forms from a field-mapping dict, so ULTRON can
handle things like "fill out this application with my saved details".
Works on plain selectors so it's usable on arbitrary sites, not tied
to one form structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from playwright.sync_api import Page

logger = logging.getLogger("ultron.form_filler")


@dataclass
class FieldSpec:
    selector: str
    value: Union[str, bool, List[str]]
    field_type: str = "text"  # "text" | "select" | "checkbox" | "radio" | "file"


class FormFiller:
    def __init__(self, page: Page):
        self.page = page

    def fill_field(self, spec: FieldSpec) -> bool:
        try:
            if spec.field_type == "text":
                self.page.fill(spec.selector, str(spec.value))
            elif spec.field_type == "select":
                self.page.select_option(spec.selector, str(spec.value))
            elif spec.field_type == "checkbox":
                checked = self.page.is_checked(spec.selector)
                if bool(spec.value) != checked:
                    self.page.click(spec.selector)
            elif spec.field_type == "radio":
                self.page.check(spec.selector)
            elif spec.field_type == "file":
                paths = spec.value if isinstance(spec.value, list) else [str(spec.value)]
                self.page.set_input_files(spec.selector, paths)
            else:
                logger.warning("Unknown field_type '%s' for %s", spec.field_type, spec.selector)
                return False
            return True
        except Exception as e:
            logger.error("Failed to fill %s: %s", spec.selector, e)
            return False

    def fill_form(self, fields: List[FieldSpec]) -> Dict[str, bool]:
        results = {}
        for spec in fields:
            results[spec.selector] = self.fill_field(spec)
        succeeded = sum(results.values())
        logger.info("Filled %d/%d fields", succeeded, len(fields))
        return results

    def fill_from_dict(self, mapping: Dict[str, str]) -> Dict[str, bool]:
        """Convenience path for the common case: {selector: text_value}."""
        return self.fill_form([FieldSpec(selector=sel, value=val) for sel, val in mapping.items()])

    def submit(self, submit_selector: Optional[str] = None) -> bool:
        try:
            if submit_selector:
                self.page.click(submit_selector)
            else:
                self.page.keyboard.press("Enter")
            logger.info("Form submitted")
            return True
        except Exception as e:
            logger.error("Submit failed: %s", e)
            return False

    def has_validation_errors(self, error_selector: str = "[aria-invalid='true'], .error, .field-error") -> bool:
        return self.page.query_selector(error_selector) is not None
