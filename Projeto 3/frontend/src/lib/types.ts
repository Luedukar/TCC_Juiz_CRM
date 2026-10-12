export type Role = 'sales_manager' | 'sales_rep'
export type Temperature = 'cold' | 'warm' | 'hot'
export type DealStatus = 'open' | 'won' | 'lost'
export type InteractionType = 'meeting' | 'email' | 'call'
export type NextActionType = 'meeting' | 'email' | 'call' | 'proposal' | 'follow_up' | 'other'

export interface User {
  id: string
  name: string
  email: string
  role: Role
  is_active: boolean
  last_login_at: string | null
  terms_accepted_at: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginResponse extends TokenPair {
  user: User
}

export interface Stage {
  id: string
  pipeline_id: string
  name: string
  position: number
  probability: number
  color: string
  is_won: boolean
  is_lost: boolean
}

export interface CompanyRef {
  id: string
  legal_name: string
  trade_name: string | null
}

export interface ContactRef {
  id: string
  full_name: string
  email: string | null
  phone: string | null
}

export interface Company extends CompanyRef {
  owner_id: string
  cnpj: string | null
}

export interface Contact extends ContactRef {
  company_id: string
  job_title: string | null
}

// O backend serializa Decimal como string (ex.: "1500.00").
export interface Deal {
  id: string
  pipeline_id: string
  stage_id: string
  title: string
  value: string
  currency: string
  temperature: Temperature
  status: DealStatus
  position: string
  expected_close_date: string | null
  next_action_type: NextActionType | null
  next_action_at: string | null
  next_action_note: string | null
  stage_entered_at: string
  closed_at: string | null
  lost_reason: string | null
  created_at: string
  updated_at: string
  company: CompanyRef
  owner: { id: string; name: string }
  primary_contact: ContactRef | null
  next_action_overdue: boolean
  days_in_stage: number
}

export interface BoardColumn {
  stage: Stage
  total_count: number
  total_value: string
  deals: Deal[]
}

export interface Board {
  pipeline_id: string
  pipeline_name: string
  columns: BoardColumn[]
  generated_at: string
}

export interface Interaction {
  id: string
  deal_id: string
  contact_id: string | null
  type: InteractionType
  subject: string
  notes: string | null
  occurred_at: string
  duration_minutes: number | null
  created_at: string
  user: { id: string; name: string }
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
