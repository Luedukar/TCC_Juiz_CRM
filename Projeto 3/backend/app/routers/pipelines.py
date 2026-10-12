import uuid

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import get_current_user, require_manager
from app.errors import BadRequest, Conflict, NotFound
from app.models import Deal, DealStageHistory, Pipeline, PipelineStage, User
from app.schemas import PipelineCreate, PipelineOut, PipelineUpdate, StageCreate, StageOut, StageReorder, StageUpdate

router = APIRouter(tags=["Funil de vendas"])


def _get_pipeline(db: Session, pipeline_id: uuid.UUID) -> Pipeline:
    pipeline = db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise NotFound("Funil não encontrado.")
    return pipeline


def _set_default(db: Session, pipeline_id: uuid.UUID) -> None:
    # Só pode existir um funil padrão (índice único parcial): zera os demais antes.
    db.execute(update(Pipeline).where(Pipeline.id != pipeline_id, Pipeline.is_default.is_(True)).values(is_default=False))


@router.get("/pipelines", response_model=list[PipelineOut])
def list_pipelines(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Pipeline).order_by(Pipeline.is_default.desc(), Pipeline.name)).all()


@router.get("/pipelines/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_pipeline(db, pipeline_id)


@router.post("/pipelines", response_model=PipelineOut, status_code=201)
def create_pipeline(body: PipelineCreate, request: Request, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
    pipeline = Pipeline(name=body.name, is_default=False)
    db.add(pipeline)
    db.flush()
    if body.is_default:
        _set_default(db, pipeline.id)
        pipeline.is_default = True
    audit(db, manager, "create", "pipeline", pipeline.id, request=request)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(
    pipeline_id: uuid.UUID, body: PipelineUpdate, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    pipeline = _get_pipeline(db, pipeline_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default") is False and pipeline.is_default:
        raise BadRequest("Defina outro funil como padrão em vez de desmarcar este.")
    if data.get("is_default"):
        _set_default(db, pipeline.id)
    for field, value in data.items():
        setattr(pipeline, field, value)
    audit(db, manager, "update", "pipeline", pipeline.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(pipeline)
    return pipeline


# ------------------------------------------------------------------ Etapas
@router.post("/pipelines/{pipeline_id}/stages", response_model=StageOut, status_code=201)
def create_stage(
    pipeline_id: uuid.UUID, body: StageCreate, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    """Adiciona a etapa ao final do funil; use PUT .../stages/order para reposicionar."""
    pipeline = _get_pipeline(db, pipeline_id)
    last = db.scalar(select(func.max(PipelineStage.position)).where(PipelineStage.pipeline_id == pipeline.id))
    stage = PipelineStage(pipeline_id=pipeline.id, position=(last + 1) if last is not None else 0, **body.model_dump())
    db.add(stage)
    db.flush()
    audit(db, manager, "create", "pipeline_stage", stage.id, request=request)
    db.commit()
    db.refresh(stage)
    return stage


@router.put("/pipelines/{pipeline_id}/stages/order", response_model=PipelineOut)
def reorder_stages(
    pipeline_id: uuid.UUID, body: StageReorder, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    pipeline = _get_pipeline(db, pipeline_id)
    current = {s.id: s for s in pipeline.stages}
    if len(body.stage_ids) != len(set(body.stage_ids)) or set(body.stage_ids) != set(current):
        raise BadRequest("A lista deve conter exatamente todas as etapas do funil, sem repetições.", code="invalid_stage_order")
    # A constraint de posição única é DEFERRABLE: a troca é validada só no commit.
    for position, stage_id in enumerate(body.stage_ids):
        current[stage_id].position = position
    audit(db, manager, "reorder", "pipeline", pipeline.id, request=request)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.patch("/stages/{stage_id}", response_model=StageOut)
def update_stage(
    stage_id: uuid.UUID, body: StageUpdate, request: Request,
    manager: User = Depends(require_manager), db: Session = Depends(get_db),
):
    stage = db.get(PipelineStage, stage_id)
    if stage is None:
        raise NotFound("Etapa não encontrada.")
    data = body.model_dump(exclude_unset=True)
    is_won = data.get("is_won", stage.is_won)
    is_lost = data.get("is_lost", stage.is_lost)
    if is_won and is_lost:
        raise BadRequest("Uma etapa não pode ser de ganho e de perda ao mesmo tempo.")
    for field, value in data.items():
        setattr(stage, field, value)
    audit(db, manager, "update", "pipeline_stage", stage.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(stage)
    return stage


@router.delete("/stages/{stage_id}", status_code=204)
def delete_stage(stage_id: uuid.UUID, request: Request, manager: User = Depends(require_manager), db: Session = Depends(get_db)):
    stage = db.get(PipelineStage, stage_id)
    if stage is None:
        raise NotFound("Etapa não encontrada.")
    # Conta também negócios excluídos (soft delete) e o histórico: ambos referenciam a etapa por FK.
    deals_linked = db.scalar(select(func.count()).select_from(Deal).where(Deal.stage_id == stage.id)) or 0
    history_linked = db.scalar(
        select(func.count()).select_from(DealStageHistory).where(
            (DealStageHistory.to_stage_id == stage.id) | (DealStageHistory.from_stage_id == stage.id)
        )
    ) or 0
    if deals_linked or history_linked:
        raise Conflict(
            "Esta etapa possui negócios ou histórico de movimentação vinculados e não pode ser excluída. "
            "Mova os negócios para outra etapa ou renomeie a etapa.",
            code="stage_in_use",
        )
    db.delete(stage)
    audit(db, manager, "delete", "pipeline_stage", stage_id, request=request)
    db.commit()
    return Response(status_code=204)
