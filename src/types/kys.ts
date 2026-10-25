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

export interface DecisionItem {
  id: number;
  topic: string;
  process_code: string;
  decision_maker: string;
  responsible?: string | null;
  consulted?: string[] | string | null;
  informed?: string[] | string | null;
  rule_id?: number | null;
  rule_summary?: string | null;
  source_document?: string | null;
  source_clause?: string | null;
  created_at?: string;
}

export interface ClauseMatchSuggestion {
  document_code: string;
  clause_no: string;
  heading?: string | null;
  quote?: string | null;
  similarity_score: number;
  explanation?: string | null;
}

export interface ImportSummaryResponse {
  ok: boolean;
  imported_count: number;
  warnings?: string[];
  message?: string;
}

export type FindingType =
  | 'CAKISMA'
  | 'BOSLUK'
  | 'GUNCELLIK'
  | 'YETKI_ASIMI'
  | 'EKSIK_ONAY'
  | 'UYGUNSUZLUK'
  | 'BELIRSIZLIK';

export type SeverityType = 'KRITIK' | 'ORTA' | 'DUSUK';

export type FindingStatus = 'ACIK' | 'KABUL' | 'YANLIS_POZITIF' | 'COZULDU';

export interface FindingItem {
  id: number;
  finding_type: FindingType;
  severity: SeverityType;
  status: FindingStatus;
  title: string;
  description: string;
  document_code?: string | null;
  process_code?: string | null;
  rule_id?: number | null;
  evidence_quote?: string | null;
  resolution_notes?: string | null;
  created_at?: string;
}

export interface AuditRunResponse {
  ok: boolean;
  run_id: string;
  findings_count: number;
  critical_count: number;
  medium_count: number;
  low_count: number;
  timestamp: string;
}

export type ComplianceVerdict = 'UYGUN' | 'SARTLI_UYGUN' | 'UYGUN_DEGIL';

export interface ComplianceCheckRequest {
  task_description: string;
  department?: string;
  budget?: number;
}

export interface ComplianceCheckResponse {
  verdict: ComplianceVerdict;
  summary: string;
  required_approvals: {
    role: string;
    condition?: string;
    rule_id?: number;
  }[];
  required_forms: {
    form_code: string;
    form_name: string;
  }[];
  required_steps: string[];
  citations: Citation[];
  model?: string;
}


