"""Program loader — reads program.md instruction files for research targets."""

from __future__ import annotations

from pathlib import Path

_PROGRAMS_DIR = Path(__file__).parent / "programs"


def load_program(target_name: str) -> str:
    """Load the program.md file for a given research target.

    Args:
        target_name: Name of the target (e.g., "code").

    Returns:
        Contents of the program file as a string.

    Raises:
        FileNotFoundError: If no program file exists for the target.
    """
    program_path = _PROGRAMS_DIR / f"{target_name}.md"
    if not program_path.exists():
        raise FileNotFoundError(
            f"No program file found for target '{target_name}' "
            f"at {program_path}"
        )
    return program_path.read_text()


def list_programs() -> list[str]:
    """List available program names."""
    if not _PROGRAMS_DIR.exists():
        return []
    return [p.stem for p in sorted(_PROGRAMS_DIR.glob("*.md"))]
