import pytest

from fundlex.upload_validation import UploadValidationError, validate_docx_upload


OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def test_legacy_doc_suffix_is_rejected_with_conversion_guidance():
    with pytest.raises(UploadValidationError) as caught:
        validate_docx_upload("合同.doc", b"legacy bytes")
    assert caught.value.code == "LEGACY_DOC_UNSUPPORTED"
    assert ".docx" in caught.value.message


def test_ole_binary_renamed_as_docx_is_rejected_as_legacy_doc():
    with pytest.raises(UploadValidationError) as caught:
        validate_docx_upload("合同.docx", OLE_MAGIC + b"legacy bytes")
    assert caught.value.code == "LEGACY_DOC_UNSUPPORTED"


def test_other_non_docx_format_keeps_generic_error():
    with pytest.raises(UploadValidationError) as caught:
        validate_docx_upload("合同.pdf", b"%PDF-1.7")
    assert caught.value.code == "UNSUPPORTED_FILE_FORMAT"
