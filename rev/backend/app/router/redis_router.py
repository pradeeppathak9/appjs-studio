import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.auth import get_current_admin_user
from app.models import User
from app.redis import redis_client

router = APIRouter(prefix="/api/admin/redis", tags=["admin-redis"])


@router.get("/keys")
def list_keys(_: User = Depends(get_current_admin_user)):
    keys = redis_client.keys("*")
    result = []
    for key in sorted(keys):
        try:
            result.append({
                "key": key,
                "type": redis_client.type(key),
                "ttl": redis_client.ttl(key),
            })
        except Exception:
            pass
    return {"keys": result}


@router.get("/keys/{key}")
def get_key(key: str, _: User = Depends(get_current_admin_user)):
    key_type = redis_client.type(key)
    if key_type == "none":
        raise HTTPException(status_code=404, detail="Key not found")

    ttl = redis_client.ttl(key)

    if key_type == "string":
        raw = redis_client.get(key)
        try:
            value = json.loads(raw)
        except Exception:
            value = raw
    elif key_type == "hash":
        value = redis_client.hgetall(key)
    elif key_type == "list":
        value = redis_client.lrange(key, 0, -1)
    elif key_type == "set":
        value = sorted(redis_client.smembers(key))
    elif key_type == "zset":
        pairs = redis_client.zrange(key, 0, -1, withscores=True)
        value = [{"member": m, "score": s} for m, s in pairs]
    else:
        value = None

    return JSONResponse({"key": key, "type": key_type, "ttl": ttl, "value": value})


@router.delete("/keys/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(key: str, _: User = Depends(get_current_admin_user)):
    deleted = redis_client.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
