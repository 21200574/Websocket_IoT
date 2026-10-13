from pydantic import BaseModel, Field
from typing import Any

class Movimiento(BaseModel):
    id_vehiculo: int = Field(gt=0)
    id_comando: int = Field(gt=0)

class EjecutarProcedimiento(BaseModel):
    parametros: dict[str, Any] = Field(default_factory=dict)
