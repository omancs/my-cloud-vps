from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.auth import get_current_user
from app.models.rule import CustomRule
from app.services.parser import parse_text_or_base64

router = APIRouter(prefix="/api/rules", tags=["rules"])


class RuleCreate(BaseModel):
    rule_type: str = "direct"       # direct / proxy / reject
    pattern: str                    # e.g. "example.com"
    match_type: str = "DOMAIN-SUFFIX"
    remark: Optional[str] = None
    priority: int = 100


class RuleUpdate(BaseModel):
    rule_type: Optional[str] = None
    pattern: Optional[str] = None
    match_type: Optional[str] = None
    remark: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class ParseTextRequest(BaseModel):
    text: str


@router.get("/")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(
        select(CustomRule).order_by(CustomRule.priority.asc(), CustomRule.id.asc())
    )
    rules = result.scalars().all()
    return [
        {
            "id": r.id, "rule_type": r.rule_type, "pattern": r.pattern,
            "match_type": r.match_type, "remark": r.remark,
            "enabled": r.enabled, "priority": r.priority,
            "created_at": r.created_at,
        }
        for r in rules
    ]


@router.post("/", status_code=201)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    rule = CustomRule(**body.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"id": rule.id, "message": "规则已添加"}


@router.put("/{rule_id}")
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(CustomRule).where(CustomRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field, value)
    await db.commit()
    return {"message": "更新成功"}


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    result = await db.execute(select(CustomRule).where(CustomRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.delete(rule)
    await db.commit()
    return {"message": "删除成功"}


@router.delete("/batch/delete")
async def batch_delete_rules(
    rule_ids: List[int],
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_user),
):
    await db.execute(delete(CustomRule).where(CustomRule.id.in_(rule_ids)))
    await db.commit()
    return {"message": f"已删除 {len(rule_ids)} 条规则"}


@router.post("/parse-text")
async def parse_nodes_from_text(
    body: ParseTextRequest,
    _: str = Depends(get_current_user),
):
    """
    Parse proxy nodes from arbitrary pasted text (clipboard input).
    Supports: URI list, Base64, multi-layer Base64, Clash YAML, mixed text.
    """
    nodes = parse_text_or_base64(body.text)
    return {
        "count": len(nodes),
        "nodes": nodes,
    }
