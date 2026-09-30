from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out

def test_scrub_cccd() -> None:
    out = scrub_text("Citizen ID: 012345678901")
    assert "012345678901" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card() -> None:
    cards = (
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "4111111111111111",
    )
    for card in cards:
        out = scrub_text(f"Pay with: {card}")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport: A1234567")
    assert "A1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_address() -> None:
    out = scrub_text("Address: 123 Main Street")
    assert "123 Main Street" not in out
    assert "REDACTED_ADDRESS" in out


def test_scrub_vn_address_keywords() -> None:
    out = scrub_text("Address: 123 Đường Lê Lợi")
    assert "123 Đường Lê Lợi" not in out
    assert "REDACTED_VN_ADDRESS_KEYWORDS" in out