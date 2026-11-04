"""AC10: README documents the credential header and carries the MSPbots
Connector section verbatim (TC11).
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


def test_readme_connector_section_matches_reference_byte_for_byte():
    """TC11 (AC10).

    The fixture is a checked-in copy of vendor-mcp-development's
    reference/readme-connector-section.md. If that template is ever updated,
    this fixture must be refreshed to match -- this test only guards against
    README drifting away from whatever the fixture currently says.
    """
    fixture_text = (REPO_ROOT / "tests" / "fixtures" / "mspbots_connector_section.md").read_text()
    readme_text = README.read_text()
    section = _extract_connector_section(readme_text)
    assert section == fixture_text


def test_readme_documents_inference_header_and_tools():
    """TC11 (AC10)."""
    text = README.read_text()
    assert "## Authentication headers" in text
    assert "X-DigitalOcean-Api-Token" in text
    assert "Personal Access Token" in text and "Model Access Key" in text, (
        "must document both ways to obtain a token"
    )
    for tool in (
        "digitalocean_inference_list_models",
        "digitalocean_inference_create_chat_completion",
        "digitalocean_inference_create_embedding",
        "digitalocean_inference_generate_image",
    ):
        assert tool in text, f"README tool table missing {tool}"
