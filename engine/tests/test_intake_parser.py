"""Phase 3 — the in-house WhatsApp chat-export parser (TECH-SPEC §2.2).

No DB. Exercises both export dialects (Android/iOS), multi-line bodies, attachment resolution,
media-less exports, system-message dropping, locale-format locking, and zip handling — the real
shapes a stranger's export throws at intake.
"""

from __future__ import annotations

import io
import zipfile

from app.intake.whatsapp_export import parse_export, parse_export_text, parse_export_zip


def test_android_thread_multiline_and_system_dropped() -> None:
    text = (
        "13/08/2026, 14:05 - Messages and calls are end-to-end encrypted.\n"
        "13/08/2026, 14:06 - Ahmed: The cake arrived crushed\n"
        "it was for a birthday\n"
        "13/08/2026, 14:07 - Ahmed: I want a refund"
    )
    msgs = parse_export_text(text)
    assert len(msgs) == 2  # the encryption system line is dropped
    assert msgs[0].sender == "Ahmed"
    # continuation line merged into the previous message's body
    assert msgs[0].text == "The cake arrived crushed\nit was for a birthday"
    assert msgs[1].text == "I want a refund"


def test_ios_bracketed_ampm_and_attachment_resolved() -> None:
    text = (
        "[13/08/2026, 2:05:33 PM] Sara: delivery was late\n"
        "[13/08/2026, 2:06:00 PM] Sara: ‎<attached: PHOTO-01.jpg>"
    )
    msgs = parse_export_text(text, attachments={"PHOTO-01.jpg": b"JPEGBYTES"})
    assert len(msgs) == 2
    assert msgs[0].text == "delivery was late"
    # the bidi mark is stripped and the attachment resolves to real bytes
    assert msgs[1].text is None
    assert len(msgs[1].attachments) == 1
    att = msgs[1].attachments[0]
    assert att.filename == "PHOTO-01.jpg"
    assert att.mime == "image/jpeg"
    assert att.data == b"JPEGBYTES"
    assert att.missing is False


def test_media_omitted_and_unresolved_attachment_marked_missing() -> None:
    text = (
        "13/08/2026, 09:00 - Ali: <Media omitted>\n"
        "13/08/2026, 09:01 - Ali: VOICE-02.opus (file attached)"
    )
    msgs = parse_export_text(text)  # no attachment bytes supplied
    assert len(msgs) == 2
    assert msgs[0].attachments[0].missing is True
    voice = msgs[1].attachments[0]
    assert voice.filename == "VOICE-02.opus"
    assert voice.mime == "audio/ogg"  # .opus override
    assert voice.missing is True


def test_locale_format_locks_to_first_parse() -> None:
    # 13 can only be a day → DD/MM locked; a later 03/08 must stay 3 Aug, not 8 Mar.
    text = "13/08/2026, 10:00 - X: first\n" "03/08/2026, 10:00 - X: second"
    msgs = parse_export_text(text)
    assert msgs[0].sent_at.month == 8 and msgs[0].sent_at.day == 13
    assert msgs[1].sent_at.month == 8 and msgs[1].sent_at.day == 3


def test_body_with_colon_keeps_sender_split_correct() -> None:
    msgs = parse_export_text("13/08/2026, 10:00 - Ahmed: see this: https://x.example/a")
    assert len(msgs) == 1
    assert msgs[0].sender == "Ahmed"
    assert msgs[0].text == "see this: https://x.example/a"


def test_parse_export_zip_autodetects_transcript_and_media() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("_chat.txt", "[13/08/2026, 2:00:00 PM] Sara: <attached: IMG-9.jpg>")
        zf.writestr("IMG-9.jpg", b"IMAGE")
    msgs = parse_export_zip(buf.getvalue())
    assert len(msgs) == 1
    assert msgs[0].attachments[0].data == b"IMAGE"


def test_captioned_media_keeps_both_attachment_and_caption() -> None:
    # H2: Android exports a captioned photo as the marker line + the caption on the next line.
    text = (
        "13/08/2026, 14:05 - Ahmed: IMG-20260813-WA0001.jpg (file attached)\n"
        "Here is the broken item, see the crack"
    )
    msgs = parse_export_text(text, attachments={"IMG-20260813-WA0001.jpg": b"JPG"})
    assert len(msgs) == 1
    assert len(msgs[0].attachments) == 1
    assert msgs[0].attachments[0].data == b"JPG"  # the photo is NOT dropped
    assert msgs[0].text == "Here is the broken item, see the crack"  # caption preserved


def test_us_locale_read_consistently_no_midfile_flip() -> None:
    # H5: a US MM/DD export must read under one calendar; message 2 (01/15) forces MM/DD and messages
    # 1 and 3 must not end up interpreted under a different (DD/MM) calendar.
    text = (
        "01/02/2026, 10:00 - A: first\n"
        "01/15/2026, 11:00 - A: second\n"
        "01/03/2026, 12:00 - A: third"
    )
    dates = [(m.sent_at.month, m.sent_at.day) for m in parse_export_text(text)]
    assert dates == [(1, 2), (1, 15), (1, 3)]  # all MM/DD: Jan 2, Jan 15, Jan 3


def test_intl_ddmm_locale_still_detected() -> None:
    dates = [
        (m.sent_at.month, m.sent_at.day)
        for m in parse_export_text("13/08/2026, 10:00 - A: x\n03/08/2026, 11:00 - A: y")
    ]
    assert dates == [(8, 13), (8, 3)]  # DD/MM: 13 Aug, 3 Aug


def test_parse_export_dispatches_by_extension() -> None:
    txt = b"13/08/2026, 10:00 - X: hi"
    assert parse_export("chat.txt", txt)[0].text == "hi"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("WhatsApp Chat with X.txt", "13/08/2026, 10:00 - X: zipped")
    assert parse_export("export.zip", buf.getvalue())[0].text == "zipped"
