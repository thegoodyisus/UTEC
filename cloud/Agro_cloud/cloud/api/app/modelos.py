#cuerpos de entrada segun openapi.yaml v1.3.0 (las respuestas se arman en main.py)
from datetime import date
from typing import Annotated, List, Literal, Optional, Union

from pydantic import UUID4, BaseModel, Field

Dinero = Annotated[str, Field(pattern=r"^[0-9]{1,9}\.[0-9]{2}$")]
Slug = Annotated[str, Field(pattern=r"^[a-z]+$", max_length=30)]
Texto = Annotated[str, Field(min_length=1, max_length=120)]
Correo = Annotated[str, Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=120)]
Volumen = Annotated[int, Field(ge=1, le=10000000)]
Logistica = Literal["Recojo", "Envio"]


class PerfilAgricultorCrear(BaseModel):
    rol: Literal["agricultor"]
    nombres: Texto
    apellidos: Texto
    tipoDoc: Literal["DNI"]
    documento: Annotated[str, Field(pattern=r"^[0-9]{8}$")]
    celular: Annotated[str, Field(pattern=r"^[0-9]{9}$")]
    correo: Optional[Correo] = None
    correoEs: Optional[Literal["mio", "familiar"]] = None
    cultivos: Annotated[List[Slug], Field(min_length=1, max_length=10)]
    departamento: Texto
    provincia: Texto
    distrito: Texto


class PerfilCompradorCrear(BaseModel):
    rol: Literal["comprador"]
    tipoDoc: Literal["RUC", "DNI"]
    documento: Annotated[str, Field(pattern=r"^([0-9]{8}|[0-9]{11})$")]
    razonSocial: Texto
    contactoNombre: Texto
    contactoCelular: Annotated[str, Field(pattern=r"^[0-9]{9}$")]
    contactoCorreo: Optional[Correo] = None
    contactoCargo: Optional[Texto] = None
    cuentaCargoId: Optional[Annotated[str, Field(pattern=r"^[a-z0-9-]{1,40}$")]] = None
    modalidadPago: Optional[Literal["recibir", "confirming"]] = None


PerfilCrear = Annotated[Union[PerfilAgricultorCrear, PerfilCompradorCrear], Field(discriminator="rol")]


class CampanaCrear(BaseModel):
    campaniaId: UUID4
    cultivo: Slug
    departamento: Texto
    provincia: Texto
    distrito: Texto
    cosecha: date
    volumenKg: Volumen
    logistica: Logistica
    capital: Dinero
    precioAhoraPorKg: Dinero
    precioContraentregaPorKg: Dinero


class CampanaActualizar(BaseModel):
    #decision 66: solo volumen y precios; al menos un campo (lo valida main.py)
    model_config = {"extra": "forbid"}
    volumenKg: Optional[Volumen] = None
    capital: Optional[Dinero] = None
    precioAhoraPorKg: Optional[Dinero] = None
    precioContraentregaPorKg: Optional[Dinero] = None


class FotoUrlSolicitud(BaseModel):
    fotoId: UUID4
    tipoContenido: Literal["image/jpeg", "image/png"]
    tamanoBytes: Annotated[int, Field(ge=1, le=5242880)]


class OfertaCrear(BaseModel):
    ofertaId: UUID4
    volumenKg: Volumen
    precioPorKg: Dinero
    modalidad: Literal["Pago ahora", "Pago contraentrega"]
    logistica: Logistica
    fechaEntrega: date


class PadronConsulta(BaseModel):
    tipoDoc: Literal["RUC", "DNI"]
    documento: Annotated[str, Field(pattern=r"^([0-9]{8}|[0-9]{11})$")]
    uso: Literal["comprador", "representante"]
