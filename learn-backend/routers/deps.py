from fastapi import Header, HTTPException
from db.supabase import supabase

async def get_current_student(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    user_resp = supabase.auth.get_user(token)
    if not user_resp or not user_resp.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    auth_user_id = str(user_resp.user.id)
    result = supabase.table("students").select("*").eq("auth_user_id", auth_user_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Student not found")
    return result.data[0]

async def get_current_admin(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    token = authorization.split(" ")[1]
    user_resp = supabase.auth.get_user(token)
    if not user_resp or not user_resp.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    email = user_resp.user.email
    result = supabase.table("admin_users").select("*").eq("email", email).eq("active", True).execute()
    if not result.data:
        raise HTTPException(status_code=403, detail="Not an admin")
    return result.data[0]