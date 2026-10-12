from datetime import datetime, timezone
import jwt
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from app.config import settings
from app.db import connection
from app.security import verify_password, issue_access, issue_refresh, decode_token, token_hash
from app.dependencies import current_user, manager_only, opportunity_scope
from app.schemas import (
    LoginIn, RefreshIn, CompanyCreate, ContactCreate, PipelineCreate, StageCreate,
    OpportunityCreate, OpportunityPatch, InteractionCreate, ConsentCreate,
)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="CRM B2B API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # Detalhes internos vão para os logs da aplicação, nunca para a resposta HTTP.
    import logging
    logging.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Ocorreu um erro interno. Tente novamente."})

@app.get("/health")
def health():
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}

@app.post("/auth/login")
@limiter.limit(settings.login_rate_limit)
def login(request: Request, data: LoginIn):
    with connection() as conn:
        user = conn.execute("SELECT id, workspace_id, full_name, email, role, password_hash FROM users WHERE lower(email)=lower(%s) AND workspace_id=%s AND is_active", (str(data.email), data.workspace_id)).fetchone()
        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")
        refresh, expires = issue_refresh(user)
        conn.execute("INSERT INTO refresh_sessions(workspace_id,user_id,token_hash,expires_at) VALUES (%s,%s,%s,%s)", (user["workspace_id"], user["id"], token_hash(refresh), expires))
    return {"access_token": issue_access(user), "refresh_token": refresh, "token_type": "bearer"}

@app.post("/auth/refresh")
def refresh_tokens(data: RefreshIn):
    try:
        claims = decode_token(data.refresh_token, "refresh")
        user_id, workspace_id = int(claims["sub"]), int(claims["workspace_id"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado")
    with connection() as conn:
        session = conn.execute("SELECT id FROM refresh_sessions WHERE workspace_id=%s AND user_id=%s AND token_hash=%s AND revoked_at IS NULL AND expires_at>now() FOR UPDATE", (workspace_id, user_id, token_hash(data.refresh_token))).fetchone()
        user = conn.execute("SELECT id,workspace_id,full_name,email,role FROM users WHERE id=%s AND workspace_id=%s AND is_active", (user_id, workspace_id)).fetchone()
        if not session or not user:
            raise HTTPException(status_code=401, detail="Sessão inválida ou revogada")
        conn.execute("UPDATE refresh_sessions SET revoked_at=%s WHERE id=%s", (datetime.now(timezone.utc), session["id"]))
        new_refresh, expires = issue_refresh(user)
        conn.execute("INSERT INTO refresh_sessions(workspace_id,user_id,token_hash,expires_at) VALUES (%s,%s,%s,%s)", (workspace_id, user_id, token_hash(new_refresh), expires))
    return {"access_token": issue_access(user), "refresh_token": new_refresh, "token_type": "bearer"}

@app.post("/auth/logout", status_code=204)
def logout(data: RefreshIn, user: dict = Depends(current_user)):
    with connection() as conn:
        conn.execute("UPDATE refresh_sessions SET revoked_at=now() WHERE workspace_id=%s AND user_id=%s AND token_hash=%s AND revoked_at IS NULL", (user["workspace_id"], user["id"], token_hash(data.refresh_token)))

@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user

@app.get("/opportunities")
def list_opportunities(user: dict = Depends(current_user), pipeline_id: int | None = None, stage_id: int | None = None):
    where, params = opportunity_scope(user)
    filters = [where, "status='open'"]
    values = list(params)
    if pipeline_id is not None:
        filters.append("pipeline_id=%s"); values.append(pipeline_id)
    if stage_id is not None:
        filters.append("stage_id=%s"); values.append(stage_id)
    with connection() as conn:
        return conn.execute("SELECT * FROM opportunities WHERE " + " AND ".join(filters) + " ORDER BY stage_id, created_at DESC", values).fetchall()

@app.post("/opportunities", status_code=201)
def create_opportunity(data: OpportunityCreate, user: dict = Depends(current_user)):
    with connection() as conn:
        stage = conn.execute("SELECT id FROM pipeline_stages WHERE id=%s AND pipeline_id=%s AND workspace_id=%s", (data.stage_id, data.pipeline_id, user["workspace_id"])).fetchone()
        if not stage: raise HTTPException(status_code=422, detail="Etapa não pertence ao funil informado")
        if data.company_id is not None:
            company = conn.execute("SELECT owner_user_id FROM companies WHERE id=%s AND workspace_id=%s", (data.company_id, user["workspace_id"])).fetchone()
            if not company or (user["role"] == "seller" and company["owner_user_id"] != user["id"]):
                raise HTTPException(status_code=404, detail="Empresa não encontrada")
        if data.primary_contact_id is not None:
            contact = conn.execute("SELECT owner_user_id,company_id FROM contacts WHERE id=%s AND workspace_id=%s", (data.primary_contact_id, user["workspace_id"])).fetchone()
            if not contact or (user["role"] == "seller" and contact["owner_user_id"] != user["id"]):
                raise HTTPException(status_code=404, detail="Contato não encontrado")
            if data.company_id is not None and contact["company_id"] not in (None, data.company_id):
                raise HTTPException(status_code=422, detail="Contato não pertence à empresa informada")
        row = conn.execute("""INSERT INTO opportunities(workspace_id,pipeline_id,stage_id,company_id,primary_contact_id,owner_user_id,title,amount,currency,temperature,expected_close_date,next_action,next_action_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""", (user["workspace_id"],data.pipeline_id,data.stage_id,data.company_id,data.primary_contact_id,user["id"],data.title,data.amount,data.currency,data.temperature,data.expected_close_date,data.next_action,data.next_action_at)).fetchone()
        return row

@app.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: int, user: dict = Depends(current_user)):
    where, params = opportunity_scope(user)
    with connection() as conn:
        row = conn.execute(f"SELECT * FROM opportunities WHERE id=%s AND {where}", (opportunity_id,*params)).fetchone()
    if not row: raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    return row

@app.patch("/opportunities/{opportunity_id}")
def update_opportunity(opportunity_id: int, data: OpportunityPatch, user: dict = Depends(current_user)):
    fields = data.model_dump(exclude_unset=True)
    if not fields: raise HTTPException(status_code=422, detail="Informe ao menos um campo")
    if "owner_user_id" in fields and user["role"] != "manager": raise HTTPException(status_code=403, detail="Somente o gestor pode transferir a carteira")
    if "stage_id" in fields:
        opportunity = get_opportunity(opportunity_id, user)
        with connection() as conn:
            stage = conn.execute("SELECT id FROM pipeline_stages WHERE id=%s AND workspace_id=%s AND pipeline_id=%s", (fields["stage_id"],user["workspace_id"],opportunity["pipeline_id"])).fetchone()
        if not stage: raise HTTPException(status_code=422, detail="Etapa inválida para o funil")
    where, params = opportunity_scope(user)
    assignments = ",".join(f"{key}=%s" for key in fields)
    values = [*fields.values(), opportunity_id, *params]
    with connection() as conn:
        row = conn.execute(f"UPDATE opportunities SET {assignments}, updated_at=now() WHERE id=%s AND {where} RETURNING *", values).fetchone()
    if not row: raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    return row

@app.get("/opportunities/{opportunity_id}/interactions")
def list_interactions(opportunity_id: int, user: dict = Depends(current_user)):
    get_opportunity(opportunity_id, user)
    with connection() as conn:
        return conn.execute("SELECT * FROM interactions WHERE workspace_id=%s AND opportunity_id=%s ORDER BY occurred_at DESC", (user["workspace_id"],opportunity_id)).fetchall()

@app.post("/opportunities/{opportunity_id}/interactions", status_code=201)
def add_interaction(opportunity_id: int, data: InteractionCreate, user: dict = Depends(current_user)):
    get_opportunity(opportunity_id, user)
    with connection() as conn:
        if data.contact_id is not None:
            contact = conn.execute("SELECT owner_user_id FROM contacts WHERE workspace_id=%s AND id=%s", (user["workspace_id"],data.contact_id)).fetchone()
            if not contact or (user["role"] == "seller" and contact["owner_user_id"] != user["id"]):
                raise HTTPException(status_code=404, detail="Contato não encontrado")
        return conn.execute("INSERT INTO interactions(workspace_id,opportunity_id,contact_id,created_by_user_id,kind,subject,body,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user["workspace_id"],opportunity_id,data.contact_id,user["id"],data.kind,data.subject,data.body,data.occurred_at)).fetchone()

@app.post("/contacts/{contact_id}/consents", status_code=201)
def record_consent(contact_id: int, data: ConsentCreate, user: dict = Depends(current_user)):
    with connection() as conn:
        contact = conn.execute("SELECT id,owner_user_id FROM contacts WHERE workspace_id=%s AND id=%s", (user["workspace_id"],contact_id)).fetchone()
        if not contact or (user["role"] == "seller" and contact["owner_user_id"] != user["id"]): raise HTTPException(status_code=404, detail="Contato não encontrado")
        return conn.execute("INSERT INTO data_consents(workspace_id,contact_id,purpose,granted,source) VALUES (%s,%s,%s,%s,%s) RETURNING *", (user["workspace_id"],contact_id,data.purpose,data.granted,data.source)).fetchone()

@app.get("/companies")
def list_companies(user: dict = Depends(current_user)):
    with connection() as conn:
        if user["role"] == "manager":
            return conn.execute("SELECT * FROM companies WHERE workspace_id=%s ORDER BY name", (user["workspace_id"],)).fetchall()
        return conn.execute("SELECT * FROM companies WHERE workspace_id=%s AND owner_user_id=%s ORDER BY name", (user["workspace_id"],user["id"])).fetchall()

@app.get("/contacts")
def list_contacts(user: dict = Depends(current_user), company_id: int | None = None):
    query = "SELECT * FROM contacts WHERE workspace_id=%s"
    values = [user["workspace_id"]]
    if user["role"] != "manager": query += " AND owner_user_id=%s"; values.append(user["id"])
    if company_id is not None: query += " AND company_id=%s"; values.append(company_id)
    query += " ORDER BY full_name"
    with connection() as conn: return conn.execute(query, values).fetchall()

@app.get("/pipelines")
def list_pipelines(user: dict = Depends(current_user)):
    with connection() as conn:
        return conn.execute("SELECT p.*, COALESCE(json_agg(s ORDER BY s.position) FILTER (WHERE s.id IS NOT NULL), '[]') AS stages FROM pipelines p LEFT JOIN pipeline_stages s ON s.workspace_id=p.workspace_id AND s.pipeline_id=p.id WHERE p.workspace_id=%s GROUP BY p.id ORDER BY p.id", (user["workspace_id"],)).fetchall()

@app.get("/users")
def list_users(user: dict = Depends(manager_only)):
    with connection() as conn:
        return conn.execute("SELECT id,full_name,email,role,is_active,created_at FROM users WHERE workspace_id=%s ORDER BY full_name", (user["workspace_id"],)).fetchall()

@app.post("/companies", status_code=201)
def create_company(data: CompanyCreate, user: dict = Depends(current_user)):
    with connection() as conn:
        return conn.execute("INSERT INTO companies(workspace_id,owner_user_id,name,legal_name,tax_id,website,industry,phone,address,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user["workspace_id"],user["id"],data.name,data.legal_name,data.tax_id,data.website,data.industry,data.phone,data.address,data.notes)).fetchone()

@app.post("/contacts", status_code=201)
def create_contact(data: ContactCreate, user: dict = Depends(current_user)):
    with connection() as conn:
        if data.company_id is not None:
            company = conn.execute("SELECT owner_user_id FROM companies WHERE workspace_id=%s AND id=%s", (user["workspace_id"],data.company_id)).fetchone()
            if not company or (user["role"] == "seller" and company["owner_user_id"] != user["id"]): raise HTTPException(status_code=404, detail="Empresa não encontrada")
        return conn.execute("INSERT INTO contacts(workspace_id,company_id,owner_user_id,full_name,email,phone,job_title,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user["workspace_id"],data.company_id,user["id"],data.full_name,str(data.email) if data.email else None,data.phone,data.job_title,data.notes)).fetchone()

@app.post("/pipelines", status_code=201)
def create_pipeline(data: PipelineCreate, user: dict = Depends(manager_only)):
    with connection() as conn:
        if data.is_default:
            conn.execute("UPDATE pipelines SET is_default=FALSE WHERE workspace_id=%s", (user["workspace_id"],))
        return conn.execute("INSERT INTO pipelines(workspace_id,name,is_default) VALUES (%s,%s,%s) RETURNING *", (user["workspace_id"],data.name,data.is_default)).fetchone()

@app.post("/pipelines/{pipeline_id}/stages", status_code=201)
def create_stage(pipeline_id: int, data: StageCreate, user: dict = Depends(manager_only)):
    if data.is_won and data.is_lost: raise HTTPException(status_code=422, detail="Etapa não pode ser ganha e perdida ao mesmo tempo")
    with connection() as conn:
        pipeline = conn.execute("SELECT id FROM pipelines WHERE workspace_id=%s AND id=%s", (user["workspace_id"],pipeline_id)).fetchone()
        if not pipeline: raise HTTPException(status_code=404, detail="Funil não encontrado")
        return conn.execute("INSERT INTO pipeline_stages(workspace_id,pipeline_id,name,position,probability,is_won,is_lost) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *", (user["workspace_id"],pipeline_id,data.name,data.position,data.probability,data.is_won,data.is_lost)).fetchone()
