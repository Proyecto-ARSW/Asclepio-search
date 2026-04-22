import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer
from app.config import settings

bearer = HTTPBearer()


def verify_token(credentials=Depends(bearer)) -> dict:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Token inválido") from e

    if payload.get("hospitalId") is None:
        raise HTTPException(status_code=403, detail="Token de pre-autenticación")

    if payload.get("rol") not in settings.allowed_roles:
        raise HTTPException(status_code=403, detail="Rol no autorizado")

    return payload
# Daniel Useche
