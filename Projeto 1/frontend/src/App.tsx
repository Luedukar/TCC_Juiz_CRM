import type { DragEvent, FormEvent, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowDownUp,
  ArrowRight,
  Bell,
  Building2,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Command,
  Filter,
  Flame,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Menu,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  UsersRound,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  clearTokens,
  Company,
  Contact,
  Deal,
  Pipeline,
  saveTokens,
  Stage,
  User,
} from "./api";

type Notice = { kind: "success" | "error"; message: string };

const money = (amount: string | number, currency = "USD") =>
  new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(Number(amount));

const shortDate = (value: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(date);
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function readableError(error: unknown): string {
  return error instanceof ApiError ? error.message : "Ocorreu um erro inesperado.";
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [loginError, setLoginError] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState("");
  const [stages, setStages] = useState<Stage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(false);
  const [boardError, setBoardError] = useState("");
  const [isStale, setIsStale] = useState(false);
  const [search, setSearch] = useState("");
  const [temperatureFilter, setTemperatureFilter] = useState("all");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [activeNav, setActiveNav] = useState("Pipeline");
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropStageId, setDropStageId] = useState<string | null>(null);
  const [clockNow, setClockNow] = useState(() => Date.now());
  const searchRef = useRef<HTMLInputElement>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadPipelines = useCallback(async () => {
    const list = await api.pipelines();
    setPipelines(list);
    setPipelineId((current) =>
      current && list.some((pipeline) => pipeline.id === current)
        ? current
        : (list.find((pipeline) => pipeline.is_default) ?? list[0])?.id ?? "",
    );
  }, []);

  const loadBoard = useCallback(
    async (showLoader = true) => {
      if (!pipelineId) {
        setStages([]);
        setDeals([]);
        setLoading(false);
        return;
      }
      if (showLoader) setLoading(true);
      setBoardError("");
      setIsStale(false);
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      refreshTimer.current = setTimeout(() => setIsStale(true), 6500);
      try {
        const [nextStages, nextDeals] = await Promise.all([
          api.stages(pipelineId),
          api.deals(pipelineId),
        ]);
        setStages(nextStages);
        setDeals(nextDeals);
      } catch (error) {
        setBoardError(readableError(error));
      } finally {
        if (refreshTimer.current) clearTimeout(refreshTimer.current);
        setLoading(false);
        setIsStale(false);
      }
    },
    [pipelineId],
  );

  useEffect(() => {
    let active = true;
    api
      .me()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch(() => {
        clearTokens();
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setCheckingSession(false);
      });
    const onSessionExpired = () => setUser(null);
    window.addEventListener("crm:session-expired", onSessionExpired);
    return () => {
      active = false;
      window.removeEventListener("crm:session-expired", onSessionExpired);
    };
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    Promise.all([loadPipelines(), api.companies(), api.contacts()])
      .then(([_, nextCompanies, nextContacts]) => {
        if (active) {
          setCompanies(nextCompanies);
          setContacts(nextContacts);
        }
      })
      .catch((error: unknown) => {
        if (active) setNotice({ kind: "error", message: readableError(error) });
      });
    return () => {
      active = false;
    };
  }, [user, loadPipelines]);

  useEffect(() => {
    if (user && pipelineId) void loadBoard();
  }, [user, pipelineId, loadBoard]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") {
        setSelectedDeal(null);
        setIsCreateOpen(false);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(null), 4200);
    return () => clearTimeout(timeout);
  }, [notice]);

  useEffect(() => {
    const timer = setInterval(() => setClockNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const filteredDeals = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");
    return deals.filter((deal) => {
      const company = companies.find((entry) => entry.id === deal.company_id)?.name ?? "";
      const searchMatches =
        !normalizedSearch ||
        deal.title.toLocaleLowerCase("pt-BR").includes(normalizedSearch) ||
        company.toLocaleLowerCase("pt-BR").includes(normalizedSearch);
      const temperatureMatches =
        temperatureFilter === "all" || deal.temperature === temperatureFilter;
      return searchMatches && temperatureMatches;
    });
  }, [deals, companies, search, temperatureFilter]);

  const totalPipelineValue = deals.reduce((sum, deal) => sum + Number(deal.amount), 0);
  const openDeals = deals.filter((deal) => !deal.closed_at && !deal.next_action);
  const overdueActions = deals.filter((deal) => {
    if (!deal.next_action_at || deal.closed_at) return false;
    return new Date(deal.next_action_at).getTime() < clockNow;
  }).length;
  const conversionProbability =
    deals.length > 0
      ? Math.round(
          deals.reduce((sum, deal) => {
            const stage = stages.find((item) => item.id === deal.stage_id);
            return sum + (stage?.probability ?? 0);
          }, 0) / deals.length,
        )
      : 0;

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginError("");
    const formData = new FormData(event.currentTarget);
    try {
      const tokens = await api.login(String(formData.get("email")), String(formData.get("password")));
      saveTokens(tokens);
      const currentUser = await api.me();
      setUser(currentUser);
    } catch (error) {
      setLoginError(readableError(error));
    }
  };

  const moveDeal = async (deal: Deal, targetStageId: string) => {
    if (deal.stage_id === targetStageId) return;
    const previousStageId = deal.stage_id;
    setDeals((current) =>
      current.map((item) =>
        item.id === deal.id ? { ...item, stage_id: targetStageId, updated_at: new Date().toISOString() } : item,
      ),
    );
    try {
      const updated = await api.moveDeal(deal.id, targetStageId);
      setDeals((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setNotice({ kind: "success", message: "Oportunidade movida para a nova etapa." });
    } catch (error) {
      setDeals((current) =>
        current.map((item) => (item.id === deal.id ? { ...item, stage_id: previousStageId } : item)),
      );
      setNotice({ kind: "error", message: readableError(error) });
    }
  };

  const saveDeal = async (event: FormEvent<HTMLFormElement>, deal?: Deal) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const data = Object.fromEntries(formData.entries());
    const companyId = String(data.company_id || "") || null;
    const contactId = String(data.primary_contact_id || "") || null;
    const amount = Number(data.amount || 0);
    const payload = {
      title: String(data.title).trim(),
      amount,
      currency: String(data.currency || "BRL"),
      temperature: String(data.temperature),
      company_id: companyId,
      primary_contact_id: contactId,
      expected_close_date: String(data.expected_close_date || "") || null,
      next_action: String(data.next_action || "").trim() || null,
      next_action_at: String(data.next_action_at || "") || null,
    };
    try {
      if (deal) {
        const updated = await api.updateDeal(deal.id, payload);
        setDeals((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        setSelectedDeal(updated);
        setNotice({ kind: "success", message: "Oportunidade atualizada." });
      } else {
        const created = await api.createDeal({
          ...payload,
          pipeline_id: pipelineId,
          stage_id: stages[0]?.id,
        });
        setDeals((current) => [created, ...current]);
        setIsCreateOpen(false);
        setNotice({ kind: "success", message: "Oportunidade criada no início do funil." });
      }
    } catch (error) {
      setNotice({ kind: "error", message: readableError(error) });
    }
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    setPipelines([]);
    setDeals([]);
    setStages([]);
  };

  if (checkingSession) {
    return (
      <main className="boot-screen">
        <div className="boot-mark"><Target size={24} /></div>
        <span>Preparando seu espaço de vendas...</span>
      </main>
    );
  }

  if (!user) return <LoginScreen onSubmit={handleLogin} error={loginError} />;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Target size={20} strokeWidth={2.5} /></div>
          <span className="brand-word">orbit<span>crm</span></span>
          <button className="icon-button sidebar-close" onClick={() => setMobileNavOpen(false)} aria-label="Fechar menu">
            <X size={18} />
          </button>
        </div>

        <div className="workspace-switch">
          <div className="workspace-avatar">N</div>
          <div className="workspace-copy"><strong>Nébula Studio</strong><span>Plano profissional</span></div>
          <ChevronDown size={15} className="muted-icon" />
        </div>

        <div className="nav-label">Workspace</div>
        <nav className="main-nav">
          <NavItem icon={<LayoutDashboard size={18} />} label="Visão geral" active={activeNav === "Visão geral"} onClick={() => setActiveNav("Visão geral")} />
          <NavItem icon={<Target size={18} />} label="Pipeline" badge={deals.length} active={activeNav === "Pipeline"} onClick={() => setActiveNav("Pipeline")} />
          <NavItem icon={<UsersRound size={18} />} label="Contatos" active={activeNav === "Contatos"} onClick={() => setActiveNav("Contatos")} />
          <NavItem icon={<Building2 size={18} />} label="Empresas" active={activeNav === "Empresas"} onClick={() => setActiveNav("Empresas")} />
          <NavItem icon={<Activity size={18} />} label="Atividades" active={activeNav === "Atividades"} onClick={() => setActiveNav("Atividades")} />
        </nav>

        <div className="nav-label nav-label-spaced">Insights</div>
        <nav className="main-nav">
          <NavItem icon={<CircleDollarSign size={18} />} label="Relatórios" active={activeNav === "Relatórios"} onClick={() => setActiveNav("Relatórios")} />
          <NavItem icon={<CalendarClock size={18} />} label="Previsões" active={activeNav === "Previsões"} onClick={() => setActiveNav("Previsões")} />
        </nav>

        <div className="sidebar-bottom">
          <div className="help-card">
            <div className="help-icon"><LifeBuoy size={17} /></div>
            <div><strong>Precisa de ajuda?</strong><span>Visite nossa central</span></div>
            <ArrowRight size={15} />
          </div>
          <button className="profile-row" onClick={handleLogout}>
            <div className="profile-avatar">{initials(user.full_name)}</div>
            <div className="profile-copy"><strong>{user.full_name}</strong><span>{user.role === "sales_manager" ? "Gestor de vendas" : "Executivo de vendas"}</span></div>
            <LogOut size={16} className="profile-logout" />
          </button>
        </div>
      </aside>

      {mobileNavOpen && <button className="mobile-scrim" onClick={() => setMobileNavOpen(false)} aria-label="Fechar menu" />}

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <button className="icon-button mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Abrir menu"><Menu size={20} /></button>
            <span>Workspace</span><ChevronRight size={14} /><strong>{activeNav}</strong>
          </div>
          <div className="topbar-actions">
            <button className="global-search" onClick={() => searchRef.current?.focus()}>
              <Search size={16} /><span>Buscar em tudo...</span><kbd><Command size={11} /> K</kbd>
            </button>
            <button className="icon-button notification-button" aria-label="Notificações"><Bell size={18} /><i /></button>
            <div className="topbar-divider" />
            <div className="topbar-user"><div className="profile-avatar small">{initials(user.full_name)}</div><ChevronDown size={14} /></div>
          </div>
        </header>

        <div className="page-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow"><span className="live-dot" /> VISÃO COMERCIAL</div>
              <h1>Pipeline de vendas</h1>
              <p>Acompanhe oportunidades e mantenha cada negociação em movimento.</p>
            </div>
            <div className="heading-actions">
              <div className="pipeline-select-wrap">
                <Target size={16} />
                <select aria-label="Selecionar funil" value={pipelineId} onChange={(event) => setPipelineId(event.target.value)}>
                  {pipelines.map((pipeline) => <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>)}
                </select>
                <ChevronDown size={14} />
              </div>
              <button className="button button-primary" onClick={() => setIsCreateOpen(true)} disabled={!stages.length}>
                <Plus size={17} /> Nova oportunidade
              </button>
            </div>
          </div>

          <section className="metric-grid" aria-label="Indicadores do pipeline">
            <MetricCard icon={<CircleDollarSign size={17} />} label="Valor no pipeline" value={money(totalPipelineValue, deals[0]?.currency ?? "BRL")} hint={`${deals.length} oportunidades ativas`} tone="blue" />
            <MetricCard icon={<Target size={17} />} label="Taxa de conversão" value={`${conversionProbability}%`} hint="Probabilidade média ponderada" tone="violet" />
            <MetricCard icon={<CalendarClock size={17} />} label="Ações atrasadas" value={String(overdueActions)} hint={overdueActions ? "Precisam da sua atenção" : "Tudo em dia por aqui"} tone={overdueActions ? "orange" : "green"} />
            <MetricCard icon={<Flame size={17} />} label="Sem próxima ação" value={String(openDeals.length)} hint="Oportunidades para acompanhar" tone="rose" />
          </section>

          <section className="board-panel">
            <div className="board-toolbar">
              <div className="board-title-group">
                <div><h2>Negociações</h2><span className="count-pill">{filteredDeals.length}</span></div>
                <span className="board-updated"><span className="sync-dot" /> Dados atualizados agora</span>
              </div>
              <div className="board-tools">
                <label className="board-search">
                  <Search size={15} />
                  <input ref={searchRef} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar oportunidades..." />
                  {search && <button onClick={() => setSearch("")} aria-label="Limpar busca"><X size={14} /></button>}
                </label>
                <label className="filter-select">
                  <Filter size={15} />
                  <select value={temperatureFilter} onChange={(event) => setTemperatureFilter(event.target.value)} aria-label="Filtrar por temperatura">
                    <option value="all">Todas</option>
                    <option value="hot">Quentes</option>
                    <option value="warm">Mornas</option>
                    <option value="cold">Frias</option>
                  </select>
                  <ChevronDown size={13} />
                </label>
                <button className="icon-button view-settings" aria-label="Configurar visualização"><SlidersHorizontal size={17} /></button>
                <button className="icon-button view-settings" aria-label="Ordenar oportunidades"><ArrowDownUp size={17} /></button>
              </div>
            </div>

            {boardError ? (
              <div className="board-state error-state">
                <div className="state-icon error-icon"><Activity size={22} /></div>
                <h3>Não foi possível carregar o pipeline</h3>
                <p>{boardError}</p>
                <button className="button button-primary" onClick={() => void loadBoard()}>Tentar novamente</button>
              </div>
            ) : loading && !deals.length ? (
              <div className="board-state loading-state">
                <div className="skeleton-columns">
                  {[0, 1, 2, 3].map((item) => <div className="skeleton-column" key={item}><i /><i /><i /></div>)}
                </div>
                <p>{isStale ? "A conexão está demorando. Ainda estamos tentando carregar..." : "Carregando suas oportunidades..."}</p>
                {isStale && <button className="text-button" onClick={() => void loadBoard(false)}>Continuar em segundo plano</button>}
              </div>
            ) : (
              <div className="board-scroll">
                {!pipelines.length && !loading ? (
                  <div className="board-state empty-state">
                    <div className="state-icon"><Target size={22} /></div>
                    <h3>Nenhum funil disponível</h3>
                    <p>Peça ao gestor para criar um funil e suas etapas.</p>
                  </div>
                ) : !stages.length && !loading ? (
                  <div className="board-state empty-state">
                    <div className="state-icon"><Settings2 size={22} /></div>
                    <h3>Este funil ainda não tem etapas</h3>
                    <p>Configure as etapas do pipeline para visualizar as oportunidades.</p>
                  </div>
                ) : (
                  <div className="kanban-grid">
                    {stages.map((stage, index) => {
                      const stageDeals = filteredDeals.filter((deal) => deal.stage_id === stage.id);
                      const stageValue = stageDeals.reduce((sum, deal) => sum + Number(deal.amount), 0);
                      return (
                        <div
                          className={`kanban-column ${dropStageId === stage.id ? "column-drag-over" : ""}`}
                          key={stage.id}
                          onDragOver={(event) => { event.preventDefault(); setDropStageId(stage.id); }}
                          onDragLeave={(event) => {
                            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropStageId(null);
                          }}
                          onDrop={(event) => {
                            event.preventDefault();
                            const deal = deals.find((item) => item.id === event.dataTransfer.getData("text/plain"));
                            if (deal) void moveDeal(deal, stage.id);
                            setDraggingId(null);
                            setDropStageId(null);
                          }}
                        >
                          <div className="column-heading">
                            <div className="column-name-row">
                              <span className={`stage-indicator stage-${index % 5}`} />
                              <h3>{stage.name}</h3>
                              <span className="column-count">{stageDeals.length}</span>
                              <button className="icon-button column-menu" aria-label={`Opções ${stage.name}`}><MoreHorizontal size={17} /></button>
                            </div>
                            <div className="column-totals"><span>{money(stageValue, stageDeals[0]?.currency ?? "BRL")}</span><span>{stage.probability}% prob.</span></div>
                            <div className="probability-track"><i style={{ width: `${stage.probability}%` }} /></div>
                          </div>
                          <div className="deal-list">
                            {stageDeals.map((deal) => (
                              <DealCard
                                key={deal.id}
                                deal={deal}
                                company={companies.find((entry) => entry.id === deal.company_id)?.name}
                                contact={contacts.find((entry) => entry.id === deal.primary_contact_id)}
                                dragging={draggingId === deal.id}
                                onDragStart={(event) => {
                                  event.dataTransfer.setData("text/plain", deal.id);
                                  event.dataTransfer.effectAllowed = "move";
                                  setDraggingId(deal.id);
                                }}
                                onDragEnd={() => { setDraggingId(null); setDropStageId(null); }}
                                onOpen={() => setSelectedDeal(deal)}
                              />
                            ))}
                            {stageDeals.length === 0 && (
                              <div className="column-empty">
                                <span>Solte oportunidades aqui</span>
                                <button onClick={() => setIsCreateOpen(true)}><Plus size={14} /> Adicionar oportunidade</button>
                              </div>
                            )}
                          </div>
                          <button className="add-deal-button" onClick={() => setIsCreateOpen(true)}><Plus size={16} /> Adicionar oportunidade</button>
                        </div>
                      );
                    })}
                    <button className="add-stage-button" onClick={() => setNotice({ kind: "error", message: "A criação de etapas está disponível pela API para gestores." })}>
                      <Plus size={17} /><span>Nova etapa</span>
                    </button>
                  </div>
                )}
              </div>
            )}
            <div className="board-footer">
              <div><span className="drag-hint-icon"><ArrowDown size={13} /></span> Arraste os cards para atualizar a etapa</div>
              <div>{filteredDeals.length} de {deals.length} oportunidades <span className="footer-separator">·</span> Atualizado há instantes</div>
            </div>
          </section>

          <div className="bottom-insight">
            <div className="insight-icon"><ShieldCheck size={17} /></div>
            <div><strong>Seu pipeline está protegido</strong><span>Os dados exibidos respeitam as permissões da sua carteira.</span></div>
            <button onClick={() => setNotice({ kind: "success", message: "A sincronização com a API está ativa." })}>Status do sistema <span className="system-online" /></button>
          </div>
        </div>
      </main>

      {(selectedDeal || isCreateOpen) && (
        <div className="drawer-layer" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) { setSelectedDeal(null); setIsCreateOpen(false); }
        }}>
          <aside className="deal-drawer" role="dialog" aria-modal="true" aria-label={selectedDeal ? "Editar oportunidade" : "Nova oportunidade"}>
            <div className="drawer-header">
              <div><span className="drawer-kicker">{selectedDeal ? "OPORTUNIDADE" : "NOVA NEGOCIAÇÃO"}</span><h2>{selectedDeal ? "Detalhes do negócio" : "Criar oportunidade"}</h2></div>
              <button className="icon-button" onClick={() => { setSelectedDeal(null); setIsCreateOpen(false); }} aria-label="Fechar"><X size={19} /></button>
            </div>
            <DealForm
              key={selectedDeal?.id ?? "new"}
              deal={selectedDeal}
              companies={companies}
              contacts={contacts}
              onSubmit={(event) => void saveDeal(event, selectedDeal ?? undefined)}
              onCancel={() => { setSelectedDeal(null); setIsCreateOpen(false); }}
            />
            {selectedDeal && <div className="drawer-meta"><span>Criado em {shortDate(selectedDeal.created_at)}</span><span>Última atualização {shortDate(selectedDeal.updated_at)}</span></div>}
          </aside>
        </div>
      )}

      {notice && <div className={`toast ${notice.kind}`} role="status"><span>{notice.kind === "success" ? <Check size={17} /> : <Activity size={17} />}</span>{notice.message}<button onClick={() => setNotice(null)} aria-label="Fechar aviso"><X size={15} /></button></div>}
    </div>
  );
}

function NavItem({ icon, label, badge, active, onClick }: { icon: ReactNode; label: string; badge?: number; active: boolean; onClick: () => void }) {
  return <button className={`nav-item ${active ? "nav-active" : ""}`} onClick={onClick}>{icon}<span>{label}</span>{badge !== undefined && <small>{badge}</small>}</button>;
}

function MetricCard({ icon, label, value, hint, tone }: { icon: React.ReactNode; label: string; value: string; hint: string; tone: string }) {
  return <article className="metric-card"><div className={`metric-icon ${tone}`}>{icon}</div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-hint"><span className={`metric-hint-dot ${tone}`} />{hint}</div></article>;
}

function DealCard({
  deal, company, contact, dragging, onDragStart, onDragEnd, onOpen,
}: {
  deal: Deal;
  company?: string;
  contact?: Contact;
  dragging: boolean;
  onDragStart: (event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
  onOpen: () => void;
}) {
  const nextActionDate = shortDate(deal.next_action_at);
  return (
    <article
      className={`deal-card ${dragging ? "deal-dragging" : ""}`}
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onOpen(); }}
      tabIndex={0}
      aria-label={`Editar oportunidade ${deal.title}`}
    >
      <div className="deal-card-top"><span className={`temperature-tag temperature-${deal.temperature}`}><i />{deal.temperature === "hot" ? "Quente" : deal.temperature === "warm" ? "Morno" : "Frio"}</span><button className="icon-button card-menu" onClick={(event) => { event.stopPropagation(); onOpen(); }} aria-label="Opções da oportunidade"><MoreHorizontal size={17} /></button></div>
      <h4>{deal.title}</h4>
      <div className="deal-company"><span className="company-mark"><Building2 size={13} /></span><span>{company || "Empresa não informada"}</span></div>
      <div className="deal-value">{money(deal.amount, deal.currency)}</div>
      {deal.next_action ? (
        <div className="next-action"><span className="action-check"><Check size={10} /></span><span>{deal.next_action}</span>{nextActionDate && <time>{nextActionDate}</time>}</div>
      ) : (
        <div className="no-next-action"><Clock3 size={13} /><span>Defina a próxima ação</span></div>
      )}
      <div className="deal-card-bottom">
        {contact ? <div className="contact-chip"><span className="contact-avatar">{initials(`${contact.first_name} ${contact.last_name}`)}</span><span>{contact.first_name} {contact.last_name}</span></div> : <div className="contact-chip no-contact"><span className="contact-avatar">?</span><span>Sem contato</span></div>}
        {deal.expected_close_date && <span className="close-date"><CalendarClock size={13} />{shortDate(deal.expected_close_date)}</span>}
      </div>
    </article>
  );
}

function DealForm({ deal, companies, contacts, onSubmit, onCancel }: {
  deal: Deal | null;
  companies: Company[];
  contacts: Contact[];
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
}) {
  const selectedCompany = deal?.company_id ?? "";
  const [companyId, setCompanyId] = useState(selectedCompany);
  const availableContacts = contacts.filter((contact) => !companyId || contact.company_id === companyId);
  return (
    <form className="deal-form" onSubmit={onSubmit}>
      <label className="form-field"><span>Nome da oportunidade <b>*</b></span><input required name="title" defaultValue={deal?.title ?? ""} placeholder="Ex.: Expansão da conta enterprise" maxLength={300} /></label>
      <div className="form-row">
        <label className="form-field"><span>Valor estimado</span><div className="amount-input"><span>R$</span><input name="amount" type="number" min="0" step="0.01" defaultValue={deal?.amount ?? "0"} /></div></label>
        <label className="form-field"><span>Moeda</span><select name="currency" defaultValue={deal?.currency ?? "BRL"}><option value="BRL">BRL</option><option value="USD">USD</option><option value="EUR">EUR</option></select></label>
      </div>
      <label className="form-field"><span>Empresa</span><select name="company_id" value={companyId} onChange={(event) => setCompanyId(event.target.value)}><option value="">Sem empresa vinculada</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
      <label className="form-field"><span>Contato principal</span><select name="primary_contact_id" defaultValue={deal?.primary_contact_id ?? ""}><option value="">Sem contato vinculado</option>{availableContacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.first_name} {contact.last_name}</option>)}</select></label>
      <label className="form-field"><span>Temperatura do lead</span><select name="temperature" defaultValue={deal?.temperature ?? "warm"}><option value="hot">🔥 Quente — alta intenção</option><option value="warm">☀️ Morno — em avaliação</option><option value="cold">❄️ Frio — relacionamento inicial</option></select></label>
      <label className="form-field"><span>Previsão de fechamento</span><input type="date" name="expected_close_date" defaultValue={deal?.expected_close_date ?? ""} /></label>
      <div className="form-section-label"><span>PRÓXIMA AÇÃO</span><i /></div>
      <label className="form-field"><span>O que precisa acontecer?</span><input name="next_action" defaultValue={deal?.next_action ?? ""} placeholder="Ex.: Enviar proposta comercial" /></label>
      <label className="form-field"><span>Data e horário</span><input type="datetime-local" name="next_action_at" defaultValue={deal?.next_action_at ? deal.next_action_at.slice(0, 16) : ""} /></label>
      <div className="drawer-actions"><button type="button" className="button button-quiet" onClick={onCancel}>Cancelar</button><button type="submit" className="button button-primary"><Check size={16} />{deal ? "Salvar alterações" : "Criar oportunidade"}</button></div>
    </form>
  );
}

function LoginScreen({ onSubmit, error }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; error: string }) {
  return (
    <main className="login-screen">
      <div className="login-decoration decoration-one" /><div className="login-decoration decoration-two" />
      <section className="login-card">
        <div className="login-brand"><div className="brand-mark"><Target size={20} strokeWidth={2.5} /></div><span className="brand-word">orbit<span>crm</span></span></div>
        <div className="login-heading"><div className="eyebrow"><span className="live-dot" /> SEU ESPAÇO DE VENDAS</div><h1>Bom ter você<br />de volta.</h1><p>Acesse sua conta para acompanhar seu pipeline.</p></div>
        <form onSubmit={onSubmit} className="login-form">
          <label className="form-field"><span>E-mail corporativo</span><input name="email" type="email" autoComplete="username" placeholder="voce@empresa.com" required /></label>
          <label className="form-field"><span>Senha <a href="mailto:suporte@orbitcrm.local">Esqueceu?</a></span><input name="password" type="password" autoComplete="current-password" placeholder="Sua senha" required /></label>
          {error && <div className="login-error"><Activity size={15} />{error}</div>}
          <button type="submit" className="button button-primary login-submit">Entrar no Orbit <ArrowRight size={17} /></button>
        </form>
        <div className="login-footer"><ShieldCheck size={15} /> Seus dados estão protegidos e criptografados.</div>
      </section>
      <div className="login-side-note"><span>FEITO PARA VENDAS B2B</span><strong>Boas relações<br />movem negócios.</strong><div className="login-note-line" /></div>
    </main>
  );
}
