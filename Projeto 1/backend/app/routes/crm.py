import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_manager
from app.models import (
    Company,
    Contact,
    DataConsent,
    Deal,
    DealStageHistory,
    Interaction,
    Pipeline,
    PipelineStage,
    User,
)
from app.schemas import (
    CompanyCreate,
    CompanyOut,
    CompanyUpdate,
    ConsentCreate,
    ConsentOut,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    DealCreate,
    DealMove,
    DealOut,
    DealUpdate,
    InteractionCreate,
    InteractionOut,
    PipelineCreate,
    PipelineOut,
    PipelineUpdate,
    StageCreate,
    StageReorder,
    StageOut,
    StageUpdate,
)

router = APIRouter(tags=["CRM"])


def _visible(query, model, user: User):
    if user.role != "sales_manager":
        query = query.where(model.owner_id == user.id)
    return query


def _company_for_user(db: Session, company_id: uuid.UUID, user: User) -> Company:
    query = select(Company).where(Company.id == company_id)
    if user.role != "sales_manager":
        query = query.where(Company.owner_id == user.id)
    company = db.scalar(query)
    if company is None:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return company


def _contact_for_user(db: Session, contact_id: uuid.UUID, user: User) -> Contact:
    query = select(Contact).where(Contact.id == contact_id)
    if user.role != "sales_manager":
        query = query.where(Contact.owner_id == user.id)
    contact = db.scalar(query)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contato não encontrado.")
    return contact


def _deal_for_user(db: Session, deal_id: uuid.UUID, user: User) -> Deal:
    query = select(Deal).where(Deal.id == deal_id)
    if user.role != "sales_manager":
        query = query.where(Deal.owner_id == user.id)
    deal = db.scalar(query)
    if deal is None:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    return deal


def _validate_relations(
    db: Session, user: User, company_id: uuid.UUID | None, contact_id: uuid.UUID | None
) -> None:
    if company_id is not None:
        _company_for_user(db, company_id, user)
    if contact_id is not None:
        contact = _contact_for_user(db, contact_id, user)
        if company_id is not None and contact.company_id not in (None, company_id):
            raise HTTPException(status_code=422, detail="O contato não pertence à empresa informada.")


def _save(db: Session, action):
    try:
        result = action()
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A operação viola uma regra de integridade dos dados.") from exc


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _visible(select(Company), Company, user)
    if q:
        query = query.where(Company.name.ilike(f"%{q}%"))
    return db.scalars(query.order_by(Company.name).limit(500)).all()


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = Company(**payload.model_dump(), owner_id=user.id)
    db.add(company)
    _save(db, lambda: None)
    db.refresh(company)
    return company


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _company_for_user(db, company_id, user)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    company = _company_for_user(db, company_id, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(company, key, value)
    company.updated_at = datetime.now(UTC)
    _save(db, lambda: None)
    db.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(company_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    company = _company_for_user(db, company_id, user)
    db.delete(company)
    _save(db, lambda: None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(
    company_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _visible(select(Contact), Contact, user)
    if company_id is not None:
        query = query.where(Contact.company_id == company_id)
    return db.scalars(query.order_by(Contact.last_name, Contact.first_name).limit(500)).all()


@router.post("/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(payload: ContactCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.company_id is not None:
        _company_for_user(db, payload.company_id, user)
    contact = Contact(**payload.model_dump(), owner_id=user.id)
    db.add(contact)
    _save(db, lambda: None)
    db.refresh(contact)
    return contact


@router.get("/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _contact_for_user(db, contact_id, user)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contact = _contact_for_user(db, contact_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("company_id") is not None:
        _company_for_user(db, changes["company_id"], user)
    for key, value in changes.items():
        setattr(contact, key, value)
    contact.updated_at = datetime.now(UTC)
    _save(db, lambda: None)
    db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    contact = _contact_for_user(db, contact_id, user)
    db.delete(contact)
    _save(db, lambda: None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pipelines", response_model=list[PipelineOut])
def list_pipelines(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Pipeline).order_by(Pipeline.name)).all()


@router.post("/pipelines", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    payload: PipelineCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    if payload.is_default:
        db.query(Pipeline).filter(Pipeline.is_default.is_(True)).update({"is_default": False})
    pipeline = Pipeline(name=payload.name, is_default=payload.is_default, created_by=user.id)
    db.add(pipeline)
    _save(db, lambda: None)
    db.refresh(pipeline)
    return pipeline


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(
    pipeline_id: uuid.UUID,
    payload: PipelineUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    pipeline = db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_default"):
        db.query(Pipeline).filter(Pipeline.is_default.is_(True), Pipeline.id != pipeline_id).update(
            {"is_default": False}
        )
    for key, value in changes.items():
        setattr(pipeline, key, value)
    pipeline.updated_at = datetime.now(UTC)
    _save(db, lambda: None)
    db.refresh(pipeline)
    return pipeline


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(
    pipeline_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    pipeline = db.get(Pipeline, pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    db.delete(pipeline)
    _save(db, lambda: None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/pipelines/{pipeline_id}/stages", response_model=list[StageOut])
def list_stages(
    pipeline_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if db.get(Pipeline, pipeline_id) is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    return db.scalars(
        select(PipelineStage).where(PipelineStage.pipeline_id == pipeline_id).order_by(PipelineStage.position)
    ).all()


@router.post("/pipelines/{pipeline_id}/stages", response_model=StageOut, status_code=status.HTTP_201_CREATED)
def create_stage(
    pipeline_id: uuid.UUID,
    payload: StageCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    if payload.is_won and payload.is_lost:
        raise HTTPException(status_code=422, detail="Uma etapa não pode ser ganha e perdida ao mesmo tempo.")
    if db.get(Pipeline, pipeline_id) is None:
        raise HTTPException(status_code=404, detail="Funil não encontrado.")
    stage = PipelineStage(pipeline_id=pipeline_id, **payload.model_dump())
    db.add(stage)
    _save(db, lambda: None)
    db.refresh(stage)
    return stage


@router.patch("/pipelines/{pipeline_id}/stages/{stage_id}", response_model=StageOut)
def update_stage(
    pipeline_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: StageUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    stage = db.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != pipeline_id:
        raise HTTPException(status_code=404, detail="Etapa não encontrada.")
    changes = payload.model_dump(exclude_unset=True)
    is_won = changes.get("is_won", stage.is_won)
    is_lost = changes.get("is_lost", stage.is_lost)
    if is_won and is_lost:
        raise HTTPException(status_code=422, detail="Uma etapa não pode ser ganha e perdida ao mesmo tempo.")
    for key, value in changes.items():
        setattr(stage, key, value)
    _save(db, lambda: None)
    db.refresh(stage)
    return stage


@router.post("/pipelines/{pipeline_id}/stages/reorder", response_model=list[StageOut])
def reorder_stages(
    pipeline_id: uuid.UUID,
    payload: StageReorder,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    stages = db.scalars(
        select(PipelineStage).where(PipelineStage.pipeline_id == pipeline_id)
    ).all()
    if not stages:
        raise HTTPException(status_code=404, detail="Etapas não encontradas para esse funil.")
    stages_by_id = {stage.id: stage for stage in stages}
    if len(payload.stage_ids) != len(stages) or set(payload.stage_ids) != set(stages_by_id):
        raise HTTPException(status_code=422, detail="Informe cada etapa do funil exatamente uma vez.")
    position_offset = max(stage.position for stage in stages) + 1
    db.query(PipelineStage).filter(PipelineStage.pipeline_id == pipeline_id).update(
        {PipelineStage.position: PipelineStage.position + position_offset},
        synchronize_session=False,
    )
    for position, stage_id in enumerate(payload.stage_ids):
        stages_by_id[stage_id].position = position
    _save(db, lambda: None)
    return db.scalars(
        select(PipelineStage).where(PipelineStage.pipeline_id == pipeline_id).order_by(PipelineStage.position)
    ).all()


@router.delete("/pipelines/{pipeline_id}/stages/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stage(
    pipeline_id: uuid.UUID,
    stage_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    stage = db.get(PipelineStage, stage_id)
    if stage is None or stage.pipeline_id != pipeline_id:
        raise HTTPException(status_code=404, detail="Etapa não encontrada.")
    db.delete(stage)
    _save(db, lambda: None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/deals", response_model=list[DealOut])
def list_deals(
    pipeline_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _visible(select(Deal), Deal, user)
    if pipeline_id is not None:
        query = query.where(Deal.pipeline_id == pipeline_id)
    if stage_id is not None:
        query = query.where(Deal.stage_id == stage_id)
    return db.scalars(query.order_by(Deal.updated_at.desc()).limit(1000)).all()


@router.post("/deals", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def create_deal(payload: DealCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = payload.model_dump()
    requested_owner = data.pop("owner_id")
    if requested_owner is not None and user.role != "sales_manager" and requested_owner != user.id:
        raise HTTPException(status_code=403, detail="Vendedores só podem criar oportunidades para a própria carteira.")
    owner_id = requested_owner if user.role == "sales_manager" and requested_owner else user.id
    stage = db.get(PipelineStage, data["stage_id"])
    if stage is None or stage.pipeline_id != data["pipeline_id"]:
        raise HTTPException(status_code=422, detail="A etapa informada não pertence ao funil.")
    _validate_relations(db, user, data.get("company_id"), data.get("primary_contact_id"))
    deal = Deal(**data, owner_id=owner_id)
    db.add(deal)
    _save(db, lambda: None)
    db.refresh(deal)
    return deal


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(deal_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _deal_for_user(db, deal_id, user)


@router.patch("/deals/{deal_id}", response_model=DealOut)
def update_deal(
    deal_id: uuid.UUID,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deal = _deal_for_user(db, deal_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if "owner_id" in changes:
        if user.role != "sales_manager":
            raise HTTPException(status_code=403, detail="Apenas o gestor pode transferir oportunidades.")
        if db.get(User, changes["owner_id"]) is None:
            raise HTTPException(status_code=422, detail="Responsável não encontrado.")
    if "company_id" in changes or "primary_contact_id" in changes:
        _validate_relations(
            db,
            user,
            changes.get("company_id", deal.company_id),
            changes.get("primary_contact_id", deal.primary_contact_id),
        )
    for key, value in changes.items():
        setattr(deal, key, value)
    deal.updated_at = datetime.now(UTC)
    _save(db, lambda: None)
    db.refresh(deal)
    return deal


@router.post("/deals/{deal_id}/stage", response_model=DealOut)
def move_deal(
    deal_id: uuid.UUID,
    payload: DealMove,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deal = _deal_for_user(db, deal_id, user)
    stage = db.get(PipelineStage, payload.stage_id)
    if stage is None or stage.pipeline_id != deal.pipeline_id:
        raise HTTPException(status_code=422, detail="A etapa informada não pertence ao funil da oportunidade.")
    if deal.stage_id == stage.id:
        return deal
    previous_stage_id = deal.stage_id
    deal.stage_id = stage.id
    deal.updated_at = datetime.now(UTC)
    deal.closed_at = deal.updated_at if stage.is_won or stage.is_lost else None
    db.add(
        DealStageHistory(
            deal_id=deal.id,
            from_stage_id=previous_stage_id,
            to_stage_id=stage.id,
            changed_by=user.id,
        )
    )
    _save(db, lambda: None)
    db.refresh(deal)
    return deal


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(deal_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    deal = _deal_for_user(db, deal_id, user)
    db.delete(deal)
    _save(db, lambda: None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/deals/{deal_id}/interactions", response_model=list[InteractionOut])
def list_interactions(
    deal_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deal_for_user(db, deal_id, user)
    return db.scalars(
        select(Interaction).where(Interaction.deal_id == deal_id).order_by(Interaction.occurred_at.desc())
    ).all()


@router.post(
    "/deals/{deal_id}/interactions",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction(
    deal_id: uuid.UUID,
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deal_for_user(db, deal_id, user)
    if payload.contact_id is not None:
        _contact_for_user(db, payload.contact_id, user)
    interaction = Interaction(
        deal_id=deal_id,
        created_by=user.id,
        **payload.model_dump(),
    )
    db.add(interaction)
    _save(db, lambda: None)
    db.refresh(interaction)
    return interaction


@router.get("/deals/{deal_id}/stage-history")
def list_stage_history(
    deal_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _deal_for_user(db, deal_id, user)
    return db.scalars(
        select(DealStageHistory)
        .where(DealStageHistory.deal_id == deal_id)
        .order_by(DealStageHistory.changed_at.desc())
    ).all()


@router.get("/contacts/{contact_id}/consents", response_model=list[ConsentOut])
def list_contact_consents(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _contact_for_user(db, contact_id, user)
    return db.scalars(
        select(DataConsent)
        .where(DataConsent.contact_id == contact_id)
        .order_by(DataConsent.recorded_at.desc())
    ).all()


@router.post(
    "/contacts/{contact_id}/consents",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
)
def record_contact_consent(
    contact_id: uuid.UUID,
    payload: ConsentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _contact_for_user(db, contact_id, user)
    consent = DataConsent(
        contact_id=contact_id,
        recorded_by=user.id,
        **payload.model_dump(),
    )
    db.add(consent)
    _save(db, lambda: None)
    db.refresh(consent)
    return consent
