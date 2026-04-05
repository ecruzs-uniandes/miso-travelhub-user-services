import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    nombre: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    telefono: str | None = None
    pais: str | None = None
    idioma: str = "es"
    moneda_preferida: str = "USD"


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
