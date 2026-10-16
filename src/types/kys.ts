export enum DocType {
  EL_KITABI = 'EL_KITABI',
  POLITIKA = 'POLITIKA',
  PROSEDUR = 'PROSEDUR',
  TALIMAT = 'TALIMAT',
  PROSES_KARTI = 'PROSES_KARTI',
  GOREV_TANIMI = 'GOREV_TANIMI',
  YETKI_MATRISI = 'YETKI_MATRISI',
  FORM = 'FORM',
  LISTE = 'LISTE',
  PLAN = 'PLAN',
  DIS_KAYNAK = 'DIS_KAYNAK',
  DIGER = 'DIGER',
}

export enum DocStatus {
  YURURLUKTE = 'YURURLUKTE',
  TASLAK = 'TASLAK',
  IPTAL = 'IPTAL',
}

export enum EntityType {
  ROL = 'ROL',
  BIRIM = 'BIRIM',
  SUREC = 'SUREC',
  FORM = 'FORM',
  KAYIT = 'KAYIT',
  SISTEM = 'SISTEM',
  KPI = 'KPI',
  STANDART_MADDESI = 'STANDART_MADDESI',
  DIS_TARAF = 'DIS_TARAF',
}

export enum RuleType {
  ONAY = 'ONAY',
  YETKI = 'YETKI',
  SORUMLULUK = 'SORUMLULUK',
  SURE = 'SURE',
  ESIK = 'ESIK',
  ZORUNLU_KAYIT = 'ZORUNLU_KAYIT',
  ZORUNLU_ADIM = 'ZORUNLU_ADIM',
  YASAK = 'YASAK',
  TETIKLEYICI = 'TETIKLEYICI',
  BILGILENDIRME = 'BILGILENDIRME',
}

export enum RelType {
  REFERANS_VERIR = 'REFERANS_VERIR',
  YERINE_GECER = 'YERINE_GECER',
  KULLANIR = 'KULLANIR',
  URETIR = 'URETIR',
  SORUMLUDUR = 'SORUMLUDUR',
  ONAYLAR = 'ONAYLAR',
  YURUTUR = 'YURUTUR',
  DANISILIR = 'DANISILIR',
  BILGILENDIRILIR = 'BILGILENDIRILIR',
  PARCASIDIR = 'PARCASIDIR',
  DAYANAGIDIR = 'DAYANAGIDIR',
  ESLESIR = 'ESLESIR',
}

export interface SectionItem {
  id: number;
  document_id: number;
  ordinal: number;
  clause_no: string | null;
  heading: string | null;
  heading_path?: string | null;
  text: string;
}

export interface DocumentItem {
  id: number;
  code: string;
  code_key: string;
  revision: string;
  title: string;
  doc_type: DocType | string;
  status: DocStatus | string;
  revision_date?: string | null;
  effective_date?: string | null;
  owner_unit?: string | null;
  summary?: string | null;
  parse_warnings?: string[];
  sections: SectionItem[];
  references: {
    ref_code: string;
    target_code?: string | null;
    target_title?: string | null;
    target_status?: string | null;
  }[];
  referenced_by: {
    code: string;
    title: string;
  }[];
}

export interface DocumentSummary {
  code: string;
  revision: string;
  title: string;
  doc_type: string;
  status: string;
  revision_date?: string | null;
  owner_unit?: string | null;
  summary?: string | null;
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
  warnings: string[];
  sections: {
    id: number;
    clause_no: string | null;
    heading: string | null;
    heading_path?: string | null;
    text: string;
  }[];
  references: {
    ref_code: string;
    target_code: string | null;
    target_title: string | null;
    target_status: string | null;
  }[];
  referenced_by: {
    code: string;
    title: string;
  }[];
}

export interface SearchResult {
  code: string;
  revision: string;
  title: string;
  clause_no: string | null;
  heading: string | null;
  section_id: number;
  text: string;
  score?: number;
}

export interface MissingDocument {
  code: string;
  referenced_from: string[];
}

export interface ReferencesResponse {
  missing_documents: MissingDocument[];
  probably_not_documents: string[];
}

export interface Citation {
  no: number;
  code: string;
  revision: string;
  clause_no: string | null;
  heading: string | null;
  title: string;
  quote: string;
  section_id?: number;
}

export interface AskResponse {
  answer: string;
  yeterli_bilgi: boolean;
  citations: Citation[];
  unverified: number;
  sources: {
    no: number;
    section_id: number;
    code: string;
    revision: string;
    clause_no: string | null;
    heading: string | null;
    title: string;
  }[];
  model: string;
}

export interface StatsResponse {
  documents: number;
  by_type: Record<string, number>;
  sections: number;
  unresolved_references: number;
  last_update: string;
}
