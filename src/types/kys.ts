export interface HealthResponse {
  ok: boolean;
  auth: boolean;
  model: string;
}

export interface StatsResponse {
  documents: number;
  rules?: number;
  pending_rules?: number;
  processes?: number;
  sections?: number;
  unresolved_references?: number;
  by_type?: Record<string, number>;
  last_update?: string;
}

export interface DocumentSummary {
  code: string;
  revision: string;
  title: string;
  doc_type: string;
  status: string;
  revision_date?: string | null;
  effective_date?: string | null;
  owner_unit?: string | null;
  summary?: string | null;
}

export interface SectionItem {
  id?: number;
  clause_no: string | null;
  heading: string | null;
  heading_path?: string | null;
  text: string;
  page?: number | null;
}

export interface ReferenceItem {
  ref_code: string;
  target_code?: string | null;
  target_title?: string | null;
  target_status?: string | null;
}

export interface ReferencedByItem {
  code: string;
  title: string;
}

export interface DocumentDetail {
  code: string;
  revision: string;
  title: string;
  doc_type: string;
  status: string;
  revision_date?: string | null;
  effective_date?: string | null;
  owner_unit?: string | null;
  summary?: string | null;
  page_count?: number;
  is_pdf?: boolean;
  sections: SectionItem[];
  references: ReferenceItem[];
  referenced_by: ReferencedByItem[];
  warnings?: string[];
}

export interface ProcessSummary {
  code: string;
  name: string;
  step_count: number;
}

export interface ProcessStep {
  seq: number;
  name: string;
  responsible?: string | null;
  decision?: string | null;
  next_steps?: string[] | null;
  quote?: string | null;
  page?: number | null;
}

export interface ProcessDetail {
  code: string;
  name: string;
  step_count?: number;
  steps: ProcessStep[];
  mermaid?: string | null;
  page_count: number;
  is_pdf: boolean;
}

export interface SearchResult {
  code: string;
  revision?: string;
  title?: string;
  clause_no: string | null;
  heading?: string | null;
  text: string;
  page?: number | null;
  score?: number;
}

export interface MissingDocument {
  code: string;
  referenced_from: string[];
}

export interface ReferencesResponse {
  missing_documents: MissingDocument[];
  probably_not_documents?: string[];
}

export interface Citation {
  doc_code: string;
  revision: string;
  clause_no: string | null;
  quote: string;
  verified: boolean;
  heading?: string | null;
  title?: string | null;
}

export interface AskResponse {
  answer: string;
  yeterli_bilgi: boolean;
  citations: Citation[];
  model?: string;
}

export interface ModelYokErrorResponse {
  detail: string;
  code: 'MODEL_YOK';
}

export type RuleStatus = 'ONERILDI' | 'ONAYLANDI' | 'DUZELTILDI' | 'REDDEDILDI';

export type RuleType =
  | 'ONAY'
  | 'YETKI'
  | 'SORUMLULUK'
  | 'SURE'
  | 'ESIK'
  | 'ZORUNLU_KAYIT'
  | 'ZORUNLU_ADIM'
  | 'YASAK'
  | 'TETIKLEYICI'
  | 'BILGILENDIRME';

export interface RuleSource {
  document: string;
  revision?: string;
  clause?: string | null;
  quote: string;
}

export interface RuleThreshold {
  value: number;
  unit: string;
  op: string;
}

export interface RuleItem {
  id: number;
  rule_type: RuleType;
  subject: string;
  action: string;
  object: string;
  condition?: string | null;
  threshold?: RuleThreshold | null;
  source: RuleSource;
  status: RuleStatus;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface EntityResolutionItem {
  id: number;
  canonical_name: string;
  entity_type: 'ROL' | 'BIRIM';
  aliases: string[];
  status: RuleStatus;
  sources?: { document: string; clause?: string | null }[];
}
