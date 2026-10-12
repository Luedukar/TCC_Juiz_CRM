import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.audit import audit
from app.database import get_db
from app.deps import get_current_user, get_owned_or_404, is_manager, resolve_owner_id, scope_owned
from app.errors import BadRequest, Forbidden, NotFound
from app.models import (
    Company, Contact, Deal, DealStageHistory, DealStatus, LeadTemperature, Pipeline, PipelineStage, User,
)
from app.pagination import paginate
from app.schemas import (
    Board, BoardColumn, DealCreate, DealMove, DealOut, DealUpdate, Page, PipelineOut, StageOut,
)
from app.security import utcnow

router = APIRouter(prefix="/deals", tags=["Negócios"])

POSITION_GAP = Decimal(1024)
MIN_GAP = Decimal("0.000002")


# ------------------------------------------------------------------ helpers
def _set_current_user(db: Session, user: User) -> None:
    """Informa o usuário ao trigger de histórico (valor local à transação)."""
    db.execute(text("SELECT set_config('app.current_user_id', :uid, true)"), {"uid": str(user.id)})


def _stage_or_400(db: Session, stage_id: uuid.UUID) -> PipelineStage:
    stage = db.get(PipelineStage, stage_id)
    if stage is None:
        raise BadRequest("Etapa não encontrada.", code="stage_not_found")
    return stage


def _check_contact_belongs(db: Session, contact_id: Optional[uuid.UUID], company_id: uuid.UUID, user: User) -> None:
    if contact_id is None:
        return
    contact = get_owned_or_404(db, Contact, contact_id, user)
    if contact.company_id != company_id:
        raise BadRequest("O contato informado não pertence à empresa do negócio.", code="contact_company_mismatch")


def _last_position(db: Session, stage_id: uuid.UUID, exclude_id: Optional[uuid.UUID] = None) -> Decimal:
    stmt = select(func.max(Deal.position)).where(Deal.stage_id == stage_id, Deal.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Deal.id != exclude_id)
    return db.scalar(stmt) or Decimal(0)


def _rebalance_column(db: Session, stage_id: uuid.UUID) -> None:
    ids = db.scalars(
        select(Deal.id).where(Deal.stage_id == stage_id, Deal.deleted_at.is_(None)).order_by(Deal.position, Deal.created_at)
    ).all()
    for index, deal_id in enumerate(ids, start=1):
        db.execute(update(Deal).where(Deal.id == deal_id).values(position=POSITION_GAP * index))
    db.flush()


def compute_position(
    db: Session, user: User, stage_id: uuid.UUID, deal_id: uuid.UUID,
    above_id: Optional[uuid.UUID], below_id: Optional[uuid.UUID], _retry: bool = True,
) -> Decimal:
    """Posição fracionária entre os cards vizinhos, evitando renumerar a coluna a cada movimento."""

    def neighbor_position(neighbor_id: Optional[uuid.UUID]) -> Optional[Decimal]:
        if neighbor_id is None:
            return None
        if neighbor_id == deal_id:
            raise BadRequest("Um card não pode ser referência de si mesmo.", code="invalid_neighbor")
        stmt = select(Deal.position).where(
            Deal.id == neighbor_id, Deal.stage_id == stage_id, Deal.deleted_at.is_(None)
        )
        position = db.scalar(scope_owned(stmt, Deal, user))
        if position is None:
            raise BadRequest("Card de referência inválido para a etapa de destino.", code="invalid_neighbor")
        return position

    above, below = neighbor_position(above_id), neighbor_position(below_id)

    if above is None and below is None:
        return _last_position(db, stage_id, deal_id) + POSITION_GAP
    if above is None:
        return below - POSITION_GAP
    if below is None:
        return above + POSITION_GAP
    if below < above:
        raise BadRequest("Ordem dos cards de referência inválida.", code="invalid_neighbor")
    if below - above < MIN_GAP:
        if not _retry:
            raise BadRequest("Não foi possível reposicionar o card. Atualize o quadro e tente novamente.")
        _rebalance_column(db, stage_id)
        return compute_position(db, user, stage_id, deal_id, above_id, below_id, _retry=False)
    return (above + below) / 2


def _default_first_stage(db: Session) -> PipelineStage:
    stage = db.scalars(
        select(PipelineStage)
        .join(Pipeline, Pipeline.id == PipelineStage.pipeline_id)
        .where(Pipeline.is_default.is_(True), PipelineStage.is_won.is_(False), PipelineStage.is_lost.is_(False))
        .order_by(PipelineStage.position)
        .limit(1)
    ).first()
    if stage is None:
        raise BadRequest("Nenhum funil padrão configurado. Peça a um gestor para configurar o funil.", code="no_default_pipeline")
    return stage


# ------------------------------------------------------------------ listagens
@router.get("", response_model=Page[DealOut])
def list_deals(
    pipeline_id: Optional[uuid.UUID] = None,
    stage_id: Optional[uuid.UUID] = None,
    owner_id: Optional[uuid.UUID] = None,
    company_id: Optional[uuid.UUID] = None,
    temperature: Optional[LeadTemperature] = None,
    status: Optional[DealStatus] = None,
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = scope_owned(select(Deal).where(Deal.deleted_at.is_(None)), Deal, user)
    filters = [
        (Deal.pipeline_id, pipeline_id), (Deal.stage_id, stage_id), (Deal.owner_id, owner_id),
        (Deal.company_id, company_id), (Deal.temperature, temperature), (Deal.status, status),
    ]
    for column, value in filters:
        if value is not None:
            stmt = stmt.where(column == value)
    if q:
        stmt = stmt.where(Deal.title.ilike(f"%{q.strip()}%"))
    return paginate(db, stmt.order_by(Deal.created_at.desc()), page, page_size)


@router.get("/board", response_model=Board)
def get_board(
    pipeline_id: Optional[uuid.UUID] = Query(None, description="Padrão: funil padrão"),
    owner_id: Optional[uuid.UUID] = Query(None, description="Gestor: filtra a carteira de um vendedor"),
    limit_per_stage: int = Query(100, ge=1, le=300),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Payload único do Kanban: colunas (etapas) com totais e cards já ordenados."""
    if pipeline_id is None:
        pipeline = db.scalars(select(Pipeline).where(Pipeline.is_default.is_(True))).first()
    else:
        pipeline = db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise NotFound("Funil não encontrado.")

    base = scope_owned(
        select(Deal).where(Deal.pipeline_id == pipeline.id, Deal.deleted_at.is_(None)), Deal, user
    )
    if owner_id is not None:
        base = base.where(Deal.owner_id == owner_id)

    # Totais por etapa (contagem e valor) independentes do limite de cards exibidos.
    base_ids = base.with_only_columns(Deal.id, Deal.stage_id, Deal.value).subquery()
    totals = {
        row.stage_id: (row.cnt, row.total)
        for row in db.execute(
            select(base_ids.c.stage_id, func.count().label("cnt"), func.coalesce(func.sum(base_ids.c.value), 0).label("total"))
            .group_by(base_ids.c.stage_id)
        )
    }

    # Top N cards por etapa via window function.
    rn = func.row_number().over(partition_by=Deal.stage_id, order_by=(Deal.position, Deal.created_at)).label("rn")
    ranked = base.with_only_columns(Deal.id, rn).subquery()
    deals = db.scalars(
        select(Deal).join(ranked, ranked.c.id == Deal.id).where(ranked.c.rn <= limit_per_stage).order_by(Deal.position, Deal.created_at)
    ).unique().all()

    by_stage: dict[uuid.UUID, list[Deal]] = {}
    for deal in deals:
        by_stage.setdefault(deal.stage_id, []).append(deal)

    columns = [
        BoardColumn(
            stage=StageOut.model_validate(stage),
            total_count=totals.get(stage.id, (0, 0))[0],
            total_value=Decimal(totals.get(stage.id, (0, 0))[1]),
            deals=[DealOut.model_validate(d) for d in by_stage.get(stage.id, [])],
        )
        for stage in pipeline.stages
    ]
    return Board(pipeline_id=pipeline.id, pipeline_name=pipeline.name, columns=columns, generated_at=utcnow())


@router.get("/next-actions", response_model=list[DealOut])
def next_actions(
    window_hours: int = Query(24, ge=0, le=24 * 30, description="Inclui atrasadas e as que vencem nas próximas N horas"),
    owner_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = scope_owned(
        select(Deal).where(
            Deal.deleted_at.is_(None), Deal.status == DealStatus.open, Deal.next_action_at.is_not(None),
            Deal.next_action_at <= utcnow() + timedelta(hours=window_hours),
        ),
        Deal, user,
    )
    if owner_id is not None:
        stmt = stmt.where(Deal.owner_id == owner_id)
    return db.scalars(stmt.order_by(Deal.next_action_at).limit(limit)).unique().all()


# ------------------------------------------------------------------ CRUD
@router.post("", response_model=DealOut, status_code=201)
def create_deal(body: DealCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = get_owned_or_404(db, Company, body.company_id, user)
    _check_contact_belongs(db, body.primary_contact_id, company.id, user)
    stage = _stage_or_400(db, body.stage_id) if body.stage_id else _default_first_stage(db)
    if stage.is_won or stage.is_lost:
        raise BadRequest("Crie o negócio em uma etapa em aberto.", code="closed_stage")

    owner_id = resolve_owner_id(db, body.owner_id, user, default=company.owner_id if is_manager(user) else None)
    deal = Deal(
        **body.model_dump(exclude={"owner_id", "stage_id"}),
        owner_id=owner_id,
        pipeline_id=stage.pipeline_id,
        stage_id=stage.id,
        position=_last_position(db, stage.id) + POSITION_GAP,
    )
    db.add(deal)
    db.flush()
    db.add(DealStageHistory(deal_id=deal.id, from_stage_id=None, to_stage_id=stage.id, moved_by=user.id))
    audit(db, user, "create", "deal", deal.id, request=request)
    db.commit()
    db.refresh(deal)
    return deal


@router.get("/{deal_id}", response_model=DealOut)
def get_deal(deal_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_or_404(db, Deal, deal_id, user)


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(
    deal_id: uuid.UUID, body: DealUpdate, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Edição rápida do formulário lateral. Para mudar de etapa use POST /deals/{id}/move."""
    deal = get_owned_or_404(db, Deal, deal_id, user)
    data = body.model_dump(exclude_unset=True)

    if "owner_id" in data and data["owner_id"] != deal.owner_id:
        data["owner_id"] = resolve_owner_id(db, data["owner_id"], user)
        if not is_manager(user):
            raise Forbidden("Apenas gestores podem transferir negócios entre vendedores.")
    if "company_id" in data:
        get_owned_or_404(db, Company, data["company_id"], user)
        if data["company_id"] != deal.company_id and "primary_contact_id" not in data:
            data["primary_contact_id"] = None  # contato antigo não pertence à nova empresa
    if data.get("primary_contact_id"):
        _check_contact_belongs(db, data["primary_contact_id"], data.get("company_id", deal.company_id), user)

    for field, value in data.items():
        setattr(deal, field, value)
    audit(db, user, "update", "deal", deal.id, {"fields": sorted(data)}, request)
    db.commit()
    db.refresh(deal)
    return deal


@router.post("/{deal_id}/move", response_model=DealOut)
def move_deal(
    deal_id: uuid.UUID, body: DealMove, request: Request,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Drag-and-drop: muda a etapa e/ou a posição do card dentro da coluna."""
    deal = get_owned_or_404(db, Deal, deal_id, user)
    stage = _stage_or_400(db, body.stage_id)
    if stage.pipeline_id != deal.pipeline_id:
        raise BadRequest("A etapa de destino não pertence ao funil deste negócio.", code="stage_pipeline_mismatch")

    lost_reason = (body.lost_reason or "").strip() or deal.lost_reason
    if stage.is_lost and not lost_reason:
        raise BadRequest("Informe o motivo da perda para mover o negócio a esta etapa.", code="lost_reason_required")

    position = compute_position(db, user, stage.id, deal.id, body.above_id, body.below_id)
    stage_changed = deal.stage_id != stage.id

    _set_current_user(db, user)  # o trigger grava quem moveu em deal_stage_history
    deal.stage_id = stage.id
    deal.position = position
    deal.lost_reason = lost_reason if stage.is_lost else None
    # status/closed_at/stage_entered_at são ajustados pelo trigger deals_on_stage_change
    if stage_changed:
        audit(db, user, "move", "deal", deal.id, {"to_stage_id": str(stage.id)}, request)
    db.commit()
    db.refresh(deal)
    return deal


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: uuid.UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deal = get_owned_or_404(db, Deal, deal_id, user)
    deal.deleted_at = utcnow()
    audit(db, user, "delete", "deal", deal.id, request=request)
    db.commit()
    return Response(status_code=204)
