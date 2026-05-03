from fastapi import APIRouter, Depends, HTTPException
from db.supabase import supabase
from routers.deps import get_current_student

router = APIRouter()

@router.get("/nodes")
async def get_nodes(student=Depends(get_current_student)):
    nodes = supabase.table("content_nodes").select("*").eq("status", "published").eq("active", True).order("display_order").execute()
    return nodes.data

@router.get("/node/{node_id}")
async def get_node(node_id: str, student=Depends(get_current_student)):
    node = supabase.table("content_nodes").select("*").eq("node_id", node_id).eq("status", "published").execute()
    if not node.data:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.data[0]

@router.get("/next")
async def get_next_node(student=Depends(get_current_student)):
    node_id = student.get("current_active_node", "F01")
    node = supabase.table("content_nodes").select("*").eq("node_id", node_id).execute()
    if not node.data:
        raise HTTPException(status_code=404, detail="No next node found")
    return node.data[0]

@router.get("/progress")
async def get_progress(student=Depends(get_current_student)):
    progress = supabase.table("unit_progress").select("*").eq("student_id", student["student_id"]).execute()
    return progress.data