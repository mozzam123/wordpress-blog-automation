"""SEO and quality validator — Phase 5.

Validates generated blog content before it is published.
Articles that fail validation must not be published.
"""

from __future__ import annotations

import logging
import re

from .models import BlogContent, ValidationResult

logger = logging.getLogger(__name__)


class SEOValidator:
    """Validates blog content for SEO and quality."""

    def validate(self, content: BlogContent) -> ValidationResult:
        """Run all validation checks. Returns ValidationResult."""
        issues: list[str] = []
        score = 100

        # Title checks
        if not content.title or len(content.title.strip()) < 10:
            issues.append("Title is missing or too short")
            score -= 25

        # SEO title length
        if len(content.seo_title) > 60:
            issues.append(f"SEO title too long ({len(content.seo_title)} > 60 chars)")
            score -= 10

        # Meta description length
        if len(content.meta_description) > 160:
            issues.append(
                f"Meta description too long ({len(content.meta_description)} > 160 chars)"
            )
            score -= 10

        # Focus keyword usage
        fk = content.focus_keyword.lower()
        if fk and fk not in content.title.lower():
            issues.append("Focus keyword not in title")
            score -= 10
        if fk and fk not in content.meta_description.lower():
            issues.append("Focus keyword not in meta description")
            score -= 10

        # Heading structure
        if not content.sections:
            issues.append("No sections found — article needs headings")
            score -= 25
        else:
            h2_count = sum(1 for s in content.sections if s.heading.strip())
            if h2_count < 2:
                issues.append(f"Too few H2 headings ({h2_count}, recommend 2+)")
                score -= 10

        # Source references
        if not content.sources:
            issues.append("No source references included")
            score -= 15

        # Readability: very long sentences
        all_text = content.introduction + " " + content.conclusion
        for section in content.sections:
            all_text += " " + section.content
        long_sentences = len(
            re.findall(r"[.!?]\s+[A-Z][^.!?]{120,}", all_text)
        )
        if long_sentences > 3:
            issues.append(f"Too many long sentences ({long_sentences})")
            score -= 10

        score = max(0, score)
        critical = [
            i
            for i in issues
            if any(w in i.lower() for w in ("missing", "too short", "no sections", "no source"))
        ]
        passed = len(critical) == 0 and score >= 60

        logger.info("Validation: passed=%s score=%d issues=%d", passed, score, len(issues))
        return ValidationResult(passed=passed, issues=issues, score=score)
