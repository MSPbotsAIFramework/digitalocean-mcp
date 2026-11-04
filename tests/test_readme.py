"""AC15: README documents the credential header and carries the MSPbots
Connector section verbatim (TC19, TC20).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
BEGIN_MARKER = "<!-- BEGIN MSPBOTS CONNECTOR SECTION"
END_MARKER = "<!-- END MSPBOTS CONNECTOR SECTION -->"


def _extract_connector_section(readme_text: str) -> str:
    start = readme_text.index(BEGIN_MARKER)
    start_of_content = readme_text.index("\n", start) + 1
    end = readme_text.index(END_MARKER, start_of_content)
    return readme_text[start_of_content:end]


def test_connector_section_matches_skill_template_verbatim():
    """TC19 (AC15).

    The fixture is a checked-in copy of vendor-mcp-development's
    reference/readme-connector-section.md. If that template is ever updated,
    this fixture must be refreshed to match (see the SOP's "all repos use
    the same text" rule) — this test only guards against README drifting
    away from whatever the fixture currently says.
    """
    fixture_text = (REPO_ROOT / "tests" / "fixtures" / "mspbots_connector_section.md").read_text()
    readme_text = README.read_text()
    section = _extract_connector_section(readme_text)
    assert section == fixture_text


def test_readme_documents_credential_header_and_creation_path():
    """TC20 (AC15)."""
    text = README.read_text()
    assert "## Authentication headers" in text
    assert "X-DigitalOcean-Api-Token" in text
    assert "Control Panel" in text and "Tokens" in text, "must document where to create the token"
