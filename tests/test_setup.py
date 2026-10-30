import pytest

from mothlit.setup import extract_code


def test_full_redirect_address():
    assert extract_code("https://httpbin.org/get?code=Ab12Cd&state=xyz", "xyz") == "Ab12Cd"


def test_httpbin_page_json():
    httpbin_json = '{\n  "args": {\n    "code": "Q9w8E7", \n    "state": "xyz"\n  }, \n  "headers": {}\n}'
    assert extract_code(httpbin_json) == "Q9w8E7"


def test_just_the_code():
    assert extract_code("  Z1y2X3 \n") == "Z1y2X3"


def test_different_state_is_rejected():
    with pytest.raises(ValueError, match="state mismatch"):
        extract_code("https://httpbin.org/get?code=Ab12Cd&state=other", "xyz")


def test_user_denied_access():
    with pytest.raises(ValueError, match="access_denied"):
        extract_code("https://httpbin.org/get?error=access_denied&state=xyz", "xyz")


@pytest.mark.parametrize("text", ["", "https://httpbin.org/get", "this has spaces"])
def test_no_code(text):
    with pytest.raises(ValueError):
        extract_code(text)
