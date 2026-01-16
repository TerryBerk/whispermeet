"""Meeting summary generation using Claude Code CLI."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MeetingSummary:
    """Structured meeting summary."""

    title: str
    date: str
    duration: str
    participants: list[str]
    tldr: str
    key_decisions: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    discussion_points: list[str] = field(default_factory=list)
    notable_quotes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Convert summary to markdown format."""
        participants_str = ", ".join(self.participants)

        lines = [
            f"# Meeting Summary: {self.title}",
            f"**Date:** {self.date}",
            f"**Duration:** {self.duration}",
            f"**Participants:** {participants_str}",
            "",
            "## TL;DR",
            self.tldr,
            "",
        ]

        if self.key_decisions:
            lines.extend(["## Key Decisions"])
            for decision in self.key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        if self.action_items:
            lines.extend(["## Action Items"])
            for item in self.action_items:
                if item.startswith("[ ]") or item.startswith("[x]"):
                    lines.append(f"- {item}")
                else:
                    lines.append(f"- [ ] {item}")
            lines.append("")

        if self.discussion_points:
            lines.extend(["## Discussion Points"])
            for i, point in enumerate(self.discussion_points, 1):
                lines.append(f"{i}. {point}")
            lines.append("")

        if self.notable_quotes:
            lines.extend(["## Notable Quotes"])
            for quote in self.notable_quotes:
                lines.append(f"> {quote}")
            lines.append("")

        return "\n".join(lines)


class SummaryGenerator:
    """Generate meeting summaries using Claude Code CLI."""

    PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

    def __init__(self, prompt_path: Optional[Path] = None):
        if prompt_path:
            self.prompt_template = prompt_path.read_text()
        else:
            default_prompt = self.PROMPTS_DIR / "summary.md"
            if default_prompt.exists():
                self.prompt_template = default_prompt.read_text()
            else:
                self.prompt_template = self._default_prompt()

    def _default_prompt(self) -> str:
        """Return default prompt if file not found."""
        return """Generate a meeting summary from the transcript.
Use English headers, content in transcript language.

Transcript:
{transcript}

Format as markdown with sections:
- TL;DR
- Key Decisions
- Action Items
- Discussion Points
"""

    def generate(
        self,
        transcript: str,
        title: str,
        date: str,
        duration: str,
        participants: list[str],
    ) -> MeetingSummary:
        """Generate summary using Claude Code CLI."""
        prompt = self.prompt_template.format(
            transcript=transcript,
            title=title,
            date=date,
            duration=duration,
            participants=", ".join(participants),
        )

        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        # Parse the markdown response
        return self._parse_response(
            result.stdout,
            title=title,
            date=date,
            duration=duration,
            participants=participants,
        )

    def _parse_response(
        self,
        response: str,
        title: str,
        date: str,
        duration: str,
        participants: list[str],
    ) -> MeetingSummary:
        """Parse Claude's markdown response into structured summary."""
        # Basic parsing - extract sections
        tldr = ""
        key_decisions = []
        action_items = []
        discussion_points = []

        current_section = None

        for line in response.split("\n"):
            line = line.strip()

            if "## TL;DR" in line:
                current_section = "tldr"
            elif "## Key Decisions" in line:
                current_section = "decisions"
            elif "## Action Items" in line:
                current_section = "actions"
            elif "## Discussion Points" in line:
                current_section = "discussion"
            elif line.startswith("## "):
                current_section = None
            elif line and current_section:
                if current_section == "tldr":
                    tldr += line + " "
                elif current_section == "decisions" and line.startswith("-"):
                    key_decisions.append(line[1:].strip())
                elif current_section == "actions" and line.startswith("-"):
                    action_items.append(line[1:].strip())
                elif current_section == "discussion":
                    discussion_points.append(line)

        return MeetingSummary(
            title=title,
            date=date,
            duration=duration,
            participants=participants,
            tldr=tldr.strip(),
            key_decisions=key_decisions,
            action_items=action_items,
            discussion_points=discussion_points,
        )
