from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer
from typing import Optional

class ToolInput(BaseModel):
    """Base class for all Data Scientist inputs."""
    pass


class MethodBlock(BaseModel):
    """HOW a computed figure was produced: the formula, what went into it, and which code ran.

    A number with no method is a claim nobody can re-derive. ``producer_sha`` names the code that
    produced it, so a reader can tell "this figure came from that formula" from "this figure came
    from whatever the producer was at the time".

    ``bound`` and ``bound_defaulted`` are separate on purpose. A bound the CALLER supplied and a
    bound the producer filled in read identically as a number, and only the second is something
    the caller never chose. ``bound_defaulted`` is ``None`` when the producer did not say, which
    is not the same as ``False``: an unmade claim is not a claim that the bound was supplied.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    formula: str
    inputs: list[str]
    bound: Optional[float] = None
    bound_defaulted: Optional[bool] = None
    producer_sha: str

    @field_validator("formula", "producer_sha")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("a method block must name its formula and its producer, not blanks")
        return v


class ToolOutput(BaseModel):
    """Base class for all Data Scientist outputs.

    ``method`` is OPTIONAL AND ADDITIVE, and additive includes the wire: an output that does not set
    it DUMPS EXACTLY WHAT IT DUMPED BEFORE — no ``method: null`` key appears in every output in the
    fleet. A subclass that already declares its own field named ``method`` keeps it, and keeps it
    when it is ``None``: only this base's own unset block is omitted.
    """
    method: Optional[MethodBlock] = None

    @model_serializer(mode="wrap")
    def _omit_an_unset_method(self, handler):
        out = handler(self)
        own = type(self).model_fields["method"].annotation == Optional[MethodBlock]
        if own and self.method is None:
            out.pop("method", None)
        return out


class DataPointer(BaseModel):
    """The secure token and URI provided by Engine DA for unstructured/structured data."""
    source: str = Field(..., description="e.g., 'minio', 'snowflake'")
    uri: str = Field(..., description="The dynamic path to the data")
    temporary_access_token: str = Field(..., description="Secure, short-lived STS token")
