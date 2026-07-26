from saathi.wa.format import to_whatsapp_text


def test_double_asterisk_becomes_whatsapp_bold():
    assert to_whatsapp_text("**Amlodipine 5mg**") == "*Amlodipine 5mg*"


def test_headings_stripped():
    assert to_whatsapp_text("## Aapke reminders") == "Aapke reminders"


def test_bullets_become_dots():
    assert to_whatsapp_text("- doodh\n- atta") == "• doodh\n• atta"


def test_markdown_link_flattened():
    assert to_whatsapp_text("[book here](https://x.co)") == "book here (https://x.co)"


def test_plain_hinglish_untouched():
    s = "Theek hai. Roz subah 8 baje reminder milega."
    assert to_whatsapp_text(s) == s


def test_excess_blank_lines_collapsed():
    assert to_whatsapp_text("a\n\n\n\nb") == "a\n\nb"


def test_business_agent_landmine_is_documented():
    """R7 guard: if someone enables Meta Business Agent on our number it becomes
    the primary responder and our pre-LLM safety classifier never runs."""
    from saathi.wa import templates
    doc = templates.__doc__ or ""
    assert "Business Agent" in doc and "rollout" in doc
