import pytest
from pydantic import ValidationError, Field
from iagent_mesh.models import ToolInput, ToolOutput, DataPointer


def test_tool_input_is_pydantic_basemodel():
    class MyInput(ToolInput):
        x: int

    instance = MyInput(x=3)
    assert instance.x == 3
    # Serialization roundtrip
    assert MyInput.model_validate({"x": 3}).x == 3


def test_tool_output_is_pydantic_basemodel():
    class MyOutput(ToolOutput):
        msg: str

    instance = MyOutput(msg="ok")
    assert instance.model_dump() == {"msg": "ok"}


def test_data_pointer_requires_all_fields():
    with pytest.raises(ValidationError):
        DataPointer()

    with pytest.raises(ValidationError):
        DataPointer(source="s3", uri="x")  # missing token


def test_data_pointer_happy_path():
    p = DataPointer(
        source="minio",
        uri="s3://bucket/path/file.parquet",
        temporary_access_token="STS-XYZ-123",
    )
    assert p.source == "minio"
    assert p.uri == "s3://bucket/path/file.parquet"
    assert p.temporary_access_token == "STS-XYZ-123"


def test_data_pointer_can_nest_under_toolinput():
    """The 02_instructor_polars template embeds DataPointer in its ToolInput."""

    class InventoryInput(ToolInput):
        target_facility: str
        document_pointer: DataPointer

    payload = {
        "target_facility": "FAC-1",
        "document_pointer": {
            "source": "s3",
            "uri": "s3://x/y",
            "temporary_access_token": "tok",
        },
    }
    inp = InventoryInput.model_validate(payload)
    assert inp.target_facility == "FAC-1"
    assert isinstance(inp.document_pointer, DataPointer)
    assert inp.document_pointer.temporary_access_token == "tok"
