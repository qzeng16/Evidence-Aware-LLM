"""Deployment regression tests for HTTP security headers."""

from pathlib import Path


PROJECT_ROOT = (
    Path(__file__).resolve().parents[1]
)


def read_text(relative_path):
    """Read one project file."""

    return (
        PROJECT_ROOT / relative_path
    ).read_text(
        encoding="utf-8"
    )


def readme_security_section():
    """Return the security-header documentation section."""

    readme = read_text("README.md")

    start_marker = (
        "<!-- security-headers:start -->"
    )

    end_marker = (
        "<!-- security-headers:end -->"
    )

    start_index = readme.index(
        start_marker
    )

    end_index = readme.index(
        end_marker
    )

    return readme[
        start_index:end_index
    ]


def test_docker_check_covers_security_contract():
    """The Docker check must validate all major response classes."""

    script = read_text(
        "scripts/security_headers_check.sh"
    )

    required_fragments = (
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "CSP unsafe-inline: absent",
        "public, max-age=3600",
        "Cache-Control: no-store",
        "HTTP 404: security headers verified",
        "HTTP 415: security headers verified",
        "HTTP 422: security headers verified",
        "Private request content absent from logs",
    )

    for fragment in required_fragments:
        assert fragment in script


def test_public_check_validates_external_demo_assets():
    """The public deployment check must load both Demo assets."""

    script = read_text(
        "scripts/hf_space.sh"
    )

    required_fragments = (
        "/assets/demo.css",
        "/assets/demo.js",
        "Public demo assets returned HTTP 200",
        'requestJson("/health"',
        'requestJson("/verify"',
        "inline assets",
    )

    for fragment in required_fragments:
        assert fragment in script


def test_documentation_and_assets_match_runtime():
    """Documentation and checked-in assets must stay consistent."""

    section = readme_security_section()

    required_documentation = (
        "X-Content-Type-Options: nosniff",
        "X-Frame-Options: DENY",
        "Referrer-Policy: no-referrer",
        "Cache-Control: no-store",
        "default-src 'none'",
        "no `'unsafe-inline'`",
        "/assets/demo.css",
        "/assets/demo.js",
        "public, max-age=3600",
        "./scripts/security_headers_check.sh",
    )

    for fragment in required_documentation:
        assert fragment in section

    web_shell = read_text(
        "app/web.py"
    )

    stylesheet = read_text(
        "app/static/demo.css"
    )

    javascript = read_text(
        "app/static/demo.js"
    )

    assert '<style>' not in web_shell
    assert '<script>' not in web_shell

    assert (
        'href="/assets/demo.css"'
        in web_shell
    )

    assert (
        'src="/assets/demo.js"'
        in web_shell
    )

    assert ":root" in stylesheet

    assert (
        'requestJson("/health"'
        in javascript
    )

    assert (
        'requestJson("/verify"'
        in javascript
    )
