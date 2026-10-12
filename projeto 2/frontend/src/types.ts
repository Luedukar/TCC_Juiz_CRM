export type User = { id: number; workspace_id: number; full_name: string; email: string; role: 'manager' | 'seller' }
export type Stage = { id: number; pipeline_id: number; name: string; position: number; probability: number; is_won: boolean; is_lost: boolean }
export type Pipeline = { id: number; name: string; is_default: boolean; stages: Stage[] }
export type Opportunity = {
  id: number; workspace_id: number; pipeline_id: number; stage_id: number; company_id: number | null;
  primary_contact_id: number | null; owner_user_id: number; title: string; amount: number | null;
  currency: string; temperature: 'cold' | 'warm' | 'hot'; status: 'open' | 'won' | 'lost';
  expected_close_date: string | null; next_action: string | null; next_action_at: string | null;
  created_at: string; updated_at: string;
}
export type Tokens = { access_token: string; refresh_token: string; token_type: string }
