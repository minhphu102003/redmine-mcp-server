import sys
from pathlib import Path
from unittest.mock import patch

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# noqa: E402 (Module level import not at top of file)
from redmine_mcp_server.security import (  # noqa: E402
    validate_redmine_url,
    SecurityValidationError,
)
import socket  # noqa: E402


def test_security():
    """Verify SSRF protection logic."""
    print("Starting SSRF Security Tests...")

    # 1. Test Public URL (Should Pass)
    try:
        validate_redmine_url("https://www.google.com")
        print("[PASS] Public URL validated successfully.")
    except Exception as e:
        print(f"[FAIL] Public URL failed: {e}")

    # 2. Test localhost (Should Fail)
    try:
        validate_redmine_url("http://localhost:8000")
        print("[FAIL] localhost was incorrectly allowed.")
    except SecurityValidationError as e:
        print(f"[PASS] localhost blocked as expected: {e}")

    # 3. Test Private IP (Should Fail)
    try:
        validate_redmine_url("http://192.168.1.1")
        print("[FAIL] Private IP was incorrectly allowed.")
    except SecurityValidationError as e:
        print(f"[PASS] Private IP blocked as expected: {e}")

    # 4. Test Cloud Metadata IP (Should Fail)
    try:
        validate_redmine_url("http://169.254.169.254/latest/meta-data/")
        print("[FAIL] Cloud metadata IP was incorrectly allowed.")
    except SecurityValidationError as e:
        print(f"[PASS] Cloud metadata IP blocked as expected: {e}")

    # 5. Test DNS Rebinding simulation (hostname resolving to private IP)
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        # Simulate a domain that points to 127.0.0.1
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
        ]
        try:
            validate_redmine_url("http://malicious-domain.com")
            print("[FAIL] DNS Rebinding (127.0.0.1) was incorrectly allowed.")
        except SecurityValidationError as e:
            print(f"[PASS] DNS Rebinding (127.0.0.1) blocked as expected: {e}")

    # 6. Test Non-Strict mode (Should Pass for private IPs)
    print("\nSwitching to non-strict mode (REDMINE_SECURITY_STRICT=false)...")
    with patch("redmine_mcp_server.security.REDMINE_SECURITY_STRICT", False):
        try:
            validate_redmine_url("http://192.168.1.1")
            print("[PASS] Private IP allowed in non-strict mode.")
        except SecurityValidationError as e:
            print(f"[FAIL] Private IP blocked even in non-strict mode: {e}")

    # 7. Test Allowlist
    print("\nTesting Hostname Allowlist...")
    with patch("redmine_mcp_server.security.REDMINE_ALLOWED_HOSTS", ["trusted.com"]):
        try:
            validate_redmine_url("https://trusted.com")
            print("[PASS] Allowlisted host allowed.")
        except SecurityValidationError as e:
            print(f"[FAIL] Allowlisted host blocked: {e}")

        try:
            validate_redmine_url("https://untrusted.com")
            print("[FAIL] Untrusted host was incorrectly allowed.")
        except SecurityValidationError as e:
            print(f"[PASS] Untrusted host blocked as expected: {e}")

    # 8. Test Redirect Hook - SSRF-via-redirect bypass
    print("\nTesting Redirect Hook (SSRF-via-redirect bypass)...")
    from redmine_mcp_server.security import ssrf_redirect_hook

    class FakeResponse:
        def __init__(self, location):
            self.is_redirect = True
            self.headers = {"Location": location}

    # Redirect to cloud metadata endpoint should be blocked
    try:
        ssrf_redirect_hook(FakeResponse("http://169.254.169.254/latest/meta-data/"))
        print("[FAIL] Redirect to metadata endpoint was incorrectly allowed.")
    except SecurityValidationError as e:
        print(f"[PASS] Redirect to metadata endpoint blocked: {e}")

    # Redirect to private IP should be blocked
    try:
        ssrf_redirect_hook(FakeResponse("http://10.0.0.1/admin"))
        print("[FAIL] Redirect to private IP was incorrectly allowed.")
    except SecurityValidationError as e:
        print(f"[PASS] Redirect to private IP blocked: {e}")

    # Redirect to public URL should be allowed
    try:
        ssrf_redirect_hook(FakeResponse("https://google.com/"))
        print("[PASS] Redirect to public URL allowed.")
    except SecurityValidationError as e:
        print(f"[FAIL] Redirect to public URL was incorrectly blocked: {e}")


if __name__ == "__main__":
    test_security()
