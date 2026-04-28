import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    nombre: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    telefono: str | None = None
    pais: str | None = None
    idioma: str = "es"
    moneda_preferida: str = "USD"
    solicita_rol: Literal["admin_hotel"] | None = None
    hotel_id_solicitado: uuid.UUID | None = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    nombre: str
    telefono: str | None
    pais: str | None
    idioma: str
    moneda_preferida: str
    mfa_activo: bool
    rol: str
    hotel_id: uuid.UUID | None = None
    solicita_rol: str | None = None
    hotel_id_solicitado: uuid.UUID | None = None
    fecha_registro: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=255)
    password: str | None = Field(None, min_length=8, max_length=128)
    telefono: str | None = None


class MFASetupResponse(BaseModel):
    secret: str
    qr_uri: str


class MFAVerifyRequest(BaseModel):
    totp_code: str


class MessageResponse(BaseModel):
    message: str


class PromoteUserRequest(BaseModel):
    email: EmailStr | None = None
    user_id: uuid.UUID | None = None
    rol: Literal["admin_hotel"]
    hotel_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate(self) -> "PromoteUserRequest":
        if bool(self.email) == bool(self.user_id):
            raise ValueError("Debe proporcionar exactamente uno de: email o user_id")
        if self.rol == "admin_hotel" and self.hotel_id is None:
            raise ValueError("hotel_id es obligatorio cuando rol es admin_hotel")
        return self


class PromotionRequestResponse(BaseModel):
    id: uuid.UUID
    email: str
    nombre: str
    solicita_rol: str
    hotel_id_solicitado: uuid.UUID | None
    fecha_registro: datetime

    model_config = {"from_attributes": True}
