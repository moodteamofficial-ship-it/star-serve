"""Provider DTOs — never expose raw provider payloads past the mapper."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DAClientCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    firstName: str
    lastName: str
    otherNames: str | None = None
    idNumber: str
    pin: str | None = None
    phone: str
    # LIVE Definite rejects certificate issue when the client was created without email.
    email: str | None = None


class DAIntermediaryCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    email: str
    phone: str
    identification: str
    krapin: str | None = None


class DAPremiumParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sumInsured: float | int | str
    capacity: str | float | int | None = None
    tonnage: str | float | int | None = None
    coverPeriod: str | int
    product: str
    coverOption: str
    transactionType: str


class DAPremiumResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    basicPremium: float | None = None
    PHCF: float | None = None
    trainingLevy: float | None = None
    stampDuty: float | None = None
    grossPremium: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
