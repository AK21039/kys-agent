import {
  HealthResponse,
  StatsResponse,
  DocumentSummary,
  DocumentDetail,
  ProcessSummary,
  ProcessDetail,
  SearchResult,
  ReferencesResponse,
  AskResponse,
  RuleItem,
  EntityResolutionItem,
  DecisionItem,
  ClauseMatchSuggestion,
  ImportSummaryResponse,
  FindingItem,
  AuditRunResponse,
  ComplianceCheckRequest,
  ComplianceCheckResponse,
  ImpactAnalysisResponse,
} from '../types/kys';

const STORAGE_KEY_API_BASE = 'kys_api_base';
const STORAGE_KEY_TOKEN = 'kys_token';
const STORAGE_KEY_LLM_PROVIDER = 'kys_llm_provider';
const STORAGE_KEY_LLM_KEY = 'kys_llm_key';

export interface LlmSessionConfig {
  provider: 'gemini' | 'anthropic';
  key: string;
}

export const getLlmSessionConfig = (): LlmSessionConfig | null => {
  try {
    const provider = sessionStorage.getItem(STORAGE_KEY_LLM_PROVIDER);
    const key = sessionStorage.getItem(STORAGE_KEY_LLM_KEY);
    if (provider && (provider === 'gemini' || provider === 'anthropic') && key && key.trim()) {
      return { provider: provider as 'gemini' | 'anthropic', key: key.trim() };
    }
  } catch {
    // ignore
  }
  return null;
};

export const setLlmSessionConfig = (provider: 'gemini' | 'anthropic', key: string): void => {
  try {
    sessionStorage.setItem(STORAGE_KEY_LLM_PROVIDER, provider);
    sessionStorage.setItem(STORAGE_KEY_LLM_KEY, key.trim());
  } catch {
    // ignore
  }
};

export const clearLlmSessionConfig = (): void => {
  try {
    sessionStorage.removeItem(STORAGE_KEY_LLM_PROVIDER);
    sessionStorage.removeItem(STORAGE_KEY_LLM_KEY);
  } catch {
    // ignore
  }
};

type UnauthorizedListener = () => void;
const unauthorizedListeners: Set<UnauthorizedListener> = new Set();

export const onUnauthorized = (listener: UnauthorizedListener): (() => void) => {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
};

const notifyUnauthorized = () => {
  unauthorizedListeners.forEach((fn) => {
    try {
      fn();
    } catch (e) {
      console.error('Error in onUnauthorized listener', e);
    }
  });
};

declare global {
  interface Window {
    KYS_API_BASE?: string;
  }
}

export const resolveApiBase = (): string => {
  // 1. localStorage.kys_api_base
  try {
    const saved = localStorage.getItem(STORAGE_KEY_API_BASE);
    if (saved && saved.trim()) {
      return saved.trim();
    }
  } catch {
    // ignore
  }

  // 2. window.KYS_API_BASE
  if (
    typeof window !== 'undefined' &&
    window.KYS_API_BASE &&
    typeof window.KYS_API_BASE === 'string' &&
    window.KYS_API_BASE.trim()
  ) {
    return window.KYS_API_BASE.trim();
  }

  // 3. import.meta.env.VITE_API_BASE
  try {
    const envBase = (import.meta as any).env?.VITE_API_BASE;
    if (envBase && typeof envBase === 'string' && envBase.trim()) {
      return envBase.trim();
    }
  } catch {
    // ignore
  }

  // 4. Uygulama /app/ altından açılmışsa: location.origin + location.pathname.replace(/\/app(\/.*)?$/, '')
  if (typeof window !== 'undefined' && window.location) {
    const { origin, pathname } = window.location;
    if (pathname && /\/app(\/.*)?$/.test(pathname)) {
      const basePath = pathname.replace(/\/app(\/.*)?$/, '');
      return `${origin}${basePath}`;
    }
  }

  return '';
};

export const getApiConfig = () => {
  let savedApiBase = '';
  let token = '';
  try {
    savedApiBase = localStorage.getItem(STORAGE_KEY_API_BASE) || '';
    token = localStorage.getItem(STORAGE_KEY_TOKEN) || '';
  } catch {
    // ignore
  }
  const apiBase = resolveApiBase();
  return { apiBase, savedApiBase, token };
};

export const setApiConfig = (apiBase: string, token: string) => {
  try {
    if (apiBase.trim()) {
      localStorage.setItem(STORAGE_KEY_API_BASE, apiBase.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY_API_BASE);
    }

    if (token.trim()) {
      localStorage.setItem(STORAGE_KEY_TOKEN, token.trim());
    } else {
      localStorage.removeItem(STORAGE_KEY_TOKEN);
    }
  } catch {
    // ignore
  }
};

const buildUrl = (path: string): string => {
  const { apiBase } = getApiConfig();
  if (!apiBase) {
    return path;
  }
  const cleanBase = apiBase.replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${cleanBase}${cleanPath}`;
};

export async function fetchWithAuth(path: string, init: RequestInit = {}): Promise<Response> {
  const url = buildUrl(path);
  const { token } = getApiConfig();

  const headers = new Headers(init.headers || {});

  // /api/health does not strictly require auth, but if token exists, we can still send or skip
  const isHealth = path.includes('/api/health');
  if (!isHealth && token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const response = await fetch(url, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    notifyUnauthorized();
    throw new Error('Yetkisiz erişim (401). Lütfen erişim token\'ınızı kontrol edin.');
  }

  return response;
}

// ---- Karar matrisi kontrolü (backend: process/decisions.py; alan adları backend'in JSON'uyla aynı) ----
export type MatrixRowStatus = 'KAYNAKLI' | 'CELISKI' | 'KISMI' | 'KAYNAK_YOK';
export type MatrixDocCheck = 'DOGRULANDI' | 'DESTEKLEMIYOR' | 'SISTEMDE_YOK';

export interface MatrixSource {
  doc_code: string | null;
  revision: string | null;
  title: string | null;
  clause_no: string | null;
  heading: string | null;
  quote: string;
  iliski: string;
  dogrulanmamis: boolean;
  kodsuz: boolean;
  dokuman_onaylayanlar: string[];
  nicelikler: string[];
}

export interface MatrixConflict {
  alan: string;
  matris: string;
  dokuman: string;
  kaynak: string;
}

export interface MatrixRowResult {
  no: number;
  sayfa: string | null;
  satir: number;
  karar: string;
  girdi: Record<string, unknown>;
  durum: MatrixRowStatus;
  aciklama: string;
  dokuman_kontrolu: MatrixDocCheck | null;
  kaynaklar: MatrixSource[];
  ilgili: MatrixSource[];
  celiskiler: MatrixConflict[];
  dogrulanmamis: boolean;
  atilan_kaynak: number;
  uyarilar: string[];
  [key: string]: unknown;
}

export interface MatrixCheckResponse {
  ozet: { toplam_satir: number; kontrol_edilen: number; sistemde_yok_dokumanlar: string[] };
  matris: { uyarilar: string[] };
  satirlar: MatrixRowResult[];
  aralik: { baslangic: number; adet: number; toplam: number };
}

async function postMatrix(file: File, params: Record<string, string>, results?: string): Promise<Response> {
  const fd = new FormData();
  fd.append('file', file);
  if (results !== undefined) fd.append('results', results);
  const headers: Record<string, string> = {};
  const sessionLlm = getLlmSessionConfig();
  if (sessionLlm) {
    headers['X-LLM-Provider'] = sessionLlm.provider;
    headers['X-LLM-Key'] = sessionLlm.key;
  }
  const res = await fetchWithAuth(`/api/decisions/check?${new URLSearchParams(params)}`, {
    method: 'POST',
    headers,
    body: fd,
  });
  if (!res.ok) {
    let msg = `Karar matrisi kontrolü başarısız (${res.status})`;
    try {
      const j = await res.json();
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  return res;
}

export const kysApi = {
  getApiConfig,
  setApiConfig,
  onUnauthorized,

  async getHealth(): Promise<HealthResponse> {
    const res = await fetchWithAuth('/api/health');
    if (!res.ok) {
      throw new Error(`Sağlık kontrolü başarısız (${res.status})`);
    }
    return res.json();
  },

  async getStats(): Promise<StatsResponse> {
    const res = await fetchWithAuth('/api/stats');
    if (!res.ok) {
      throw new Error(`İstatistikler alınamadı (${res.status})`);
    }
    return res.json();
  },

  async getDocuments(docType?: string): Promise<DocumentSummary[]> {
    const q = docType && docType !== 'HEPSI' ? `?doc_type=${encodeURIComponent(docType)}` : '';
    const res = await fetchWithAuth(`/api/documents${q}`);
    if (!res.ok) {
      throw new Error(`Dokümanlar alınamadı (${res.status})`);
    }
    return res.json();
  },

  async getDocument(code: string): Promise<DocumentDetail> {
    const res = await fetchWithAuth(`/api/documents/${encodeURIComponent(code)}`);
    if (!res.ok) {
      throw new Error(`Doküman ayrıntısı alınamadı (${res.status}): ${code}`);
    }
    return res.json();
  },

  async getPageImageUrl(code: string, pageNumber: number): Promise<string> {
    const res = await fetchWithAuth(`/api/documents/${encodeURIComponent(code)}/pages/${pageNumber}.png`, {
      headers: { Accept: 'image/png,image/*' },
    });
    if (!res.ok) {
      throw new Error(`Sayfa görüntüsü alınamadı (${res.status}): sayfa ${pageNumber}`);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },

  async getProcesses(): Promise<ProcessSummary[]> {
    const res = await fetchWithAuth('/api/processes');
    if (!res.ok) {
      throw new Error(`Süreçler alınamadı (${res.status})`);
    }
    return res.json();
  },

  async getProcess(code: string): Promise<ProcessDetail> {
    const res = await fetchWithAuth(`/api/processes/${encodeURIComponent(code)}`);
    if (!res.ok) {
      throw new Error(`Süreç ayrıntısı alınamadı (${res.status}): ${code}`);
    }
    return res.json();
  },

  async search(query: string, limit = 20): Promise<SearchResult[]> {
    const res = await fetchWithAuth(`/api/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    if (!res.ok) {
      throw new Error(`Arama başarısız (${res.status})`);
    }
    return res.json();
  },

  async getReferences(): Promise<ReferencesResponse> {
    const res = await fetchWithAuth('/api/references');
    if (!res.ok) {
      throw new Error(`Eksik atıflar alınamadı (${res.status})`);
    }
    return res.json();
  },

  getLlmSessionConfig,
  setLlmSessionConfig,
  clearLlmSessionConfig,

  async ask(question: string): Promise<AskResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // 1. Varsayılan akışta X-LLM-* başlıkları eklenmez. Yalnızca sessionStorage'da kullanıcı anahtarı varsa ekle.
    const sessionLlm = getLlmSessionConfig();
    if (sessionLlm?.provider && sessionLlm?.key) {
      headers['X-LLM-Provider'] = sessionLlm.provider;
      headers['X-LLM-Key'] = sessionLlm.key;
    }

    const res = await fetchWithAuth('/api/ask', {
      method: 'POST',
      headers,
      body: JSON.stringify({ question }),
    });

    if (!res.ok) {
      // 2. HTTP 503 ve gövdede üst düzey alan {"detail": "...", "code": "MODEL_YOK"}
      if (res.status === 503) {
        let errorData: any = null;
        try {
          errorData = await res.json();
        } catch {
          // ignore parse error
        }

        if (errorData && errorData.code === 'MODEL_YOK') {
          const detailMsg = typeof errorData.detail === 'string'
            ? errorData.detail
            : 'Kullanılabilir LLM modeli bulunamadı.';
          const modelYokError = new Error(detailMsg);
          (modelYokError as any).isModelYok = true;
          (modelYokError as any).code = 'MODEL_YOK';
          (modelYokError as any).detail = detailMsg;
          throw modelYokError;
        }
      }

      // Diğer hatalar (400, 404, 500 vb.)
      let errorMsg = `Soru yanıtlama başarısız (${res.status})`;
      try {
        const errorJson = await res.json();
        if (errorJson && errorJson.detail) {
          errorMsg = typeof errorJson.detail === 'string'
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
        }
      } catch {
        // ignore parse error
      }
      throw new Error(errorMsg);
    }

    return res.json();
  },

  async getRules(params?: {
    status?: string;
    doc_code?: string;
    rule_type?: string;
    limit?: number;
  }): Promise<RuleItem[]> {
    const q = new URLSearchParams();
    if (params?.status && params.status !== 'HEPSI') q.set('status', params.status);
    if (params?.doc_code) q.set('doc_code', params.doc_code);
    if (params?.rule_type && params.rule_type !== 'HEPSI') q.set('rule_type', params.rule_type);
    if (params?.limit) q.set('limit', String(params.limit));

    const qs = q.toString() ? `?${q.toString()}` : '';
    const res = await fetchWithAuth(`/api/rules${qs}`);
    if (!res.ok) {
      throw new Error(`Kurallar alınamadı (${res.status})`);
    }
    return res.json();
  },

  async approveRule(id: number): Promise<RuleItem> {
    const res = await fetchWithAuth(`/api/rules/${id}/approve`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Kural onaylama başarısız (${res.status})`);
    }
    return res.json();
  },

  async rejectRule(id: number, reason?: string): Promise<RuleItem> {
    const res = await fetchWithAuth(`/api/rules/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    if (!res.ok) {
      throw new Error(`Kural reddetme başarısız (${res.status})`);
    }
    return res.json();
  },

  async updateRule(id: number, updates: Partial<RuleItem>): Promise<RuleItem> {
    const res = await fetchWithAuth(`/api/rules/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    if (!res.ok) {
      throw new Error(`Kural güncelleme başarısız (${res.status})`);
    }
    return res.json();
  },

  async getEntityResolutions(status?: string): Promise<EntityResolutionItem[]> {
    const q = status && status !== 'HEPSI' ? `?status=${encodeURIComponent(status)}` : '';
    const res = await fetchWithAuth(`/api/entities/resolutions${q}`);
    if (!res.ok) {
      throw new Error(`Varlık eşlemeleri alınamadı (${res.status})`);
    }
    return res.json();
  },

  async approveEntityResolution(id: number): Promise<EntityResolutionItem> {
    const res = await fetchWithAuth(`/api/entities/resolutions/${id}/approve`, {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Varlık eşleme onaylanamadı (${res.status})`);
    }
    return res.json();
  },

  async updateEntityResolution(id: number, canonicalName: string): Promise<EntityResolutionItem> {
    const res = await fetchWithAuth(`/api/entities/resolutions/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ canonical_name: canonicalName }),
    });
    if (!res.ok) {
      throw new Error(`Varlık eşleme güncellenemedi (${res.status})`);
    }
    return res.json();
  },

  async getDecisions(processCode?: string): Promise<DecisionItem[]> {
    const q = processCode ? `?process_code=${encodeURIComponent(processCode)}` : '';
    const res = await fetchWithAuth(`/api/decisions${q}`);
    if (!res.ok) {
      throw new Error(`Karar envanteri alınamadı (${res.status})`);
    }
    return res.json();
  },

  async createOrUpdateDecision(decision: Partial<DecisionItem>): Promise<DecisionItem> {
    const res = await fetchWithAuth('/api/decisions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(decision),
    });
    if (!res.ok) {
      throw new Error(`Karar kaydedilemedi (${res.status})`);
    }
    return res.json();
  },

  async deleteDecision(id: number): Promise<{ ok: boolean }> {
    const res = await fetchWithAuth(`/api/decisions/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      throw new Error(`Karar silinemedi (${res.status})`);
    }
    return res.json();
  },

  async suggestClauseMatches(processCode: string, stepSeq: number): Promise<ClauseMatchSuggestion[]> {
    const res = await fetchWithAuth(
      `/api/processes/${encodeURIComponent(processCode)}/steps/${stepSeq}/match-clauses`,
      { method: 'POST' }
    );
    if (!res.ok) {
      throw new Error(`Madde eşleşme önerileri alınamadı (${res.status})`);
    }
    return res.json();
  },

  async linkStepClause(
    processCode: string,
    stepSeq: number,
    docCode: string,
    clauseNo: string
  ): Promise<{ ok: boolean }> {
    const res = await fetchWithAuth(
      `/api/processes/${encodeURIComponent(processCode)}/steps/${stepSeq}/link-clause`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_code: docCode, clause_no: clauseNo }),
      }
    );
    if (!res.ok) {
      throw new Error(`Adım doküman maddesine bağlanamadı (${res.status})`);
    }
    return res.json();
  },

  async importProcessExcel(file: File): Promise<ImportSummaryResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const { apiBase } = getApiConfig();
    const cleanBase = apiBase ? apiBase.replace(/\/+$/, '') : '';
    const url = `${cleanBase}/api/processes/import`;

    const { token } = getApiConfig();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!res.ok) {
      let errMsg = `Süreç Excel içe aktarma başarısız (${res.status})`;
      try {
        const j = await res.json();
        if (j.detail) errMsg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        // ignore
      }
      throw new Error(errMsg);
    }
    return res.json();
  },

  async importDecisionsExcel(file: File): Promise<ImportSummaryResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const { apiBase } = getApiConfig();
    const cleanBase = apiBase ? apiBase.replace(/\/+$/, '') : '';
    const url = `${cleanBase}/api/decisions/import`;

    const { token } = getApiConfig();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!res.ok) {
      let errMsg = `Karar Excel içe aktarma başarısız (${res.status})`;
      try {
        const j = await res.json();
        if (j.detail) errMsg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        // ignore
      }
      throw new Error(errMsg);
    }
    return res.json();
  },

  /** Karar matrisini (xlsx/csv) KYS dokümanlarına karşı kontrol eder (backend: POST /api/decisions/check).
   *  Uzun istek zaman aşımına uğramasın diye satırlar `offset`/`limit` ile parça parça istenir. Dosya saklanmaz. */
  async checkDecisionMatrix(file: File, offset: number, limit: number): Promise<MatrixCheckResponse> {
    const res = await postMatrix(file, { offset: String(offset), limit: String(limit) });
    return res.json();
  },

  /** Önceden alınmış satır sonuçlarını orijinal dosyaya kolon olarak ekleyip Excel döndürür; LLM çağrısı yapmaz. */
  async downloadDecisionMatrixXlsx(file: File, rows: MatrixRowResult[]): Promise<Blob> {
    const res = await postMatrix(file, { format: 'xlsx' }, JSON.stringify(rows));
    return res.blob();
  },

  async getFindings(params?: {
    status?: string;
    severity?: string;
    finding_type?: string;
    limit?: number;
  }): Promise<FindingItem[]> {
    const q = new URLSearchParams();
    if (params?.status && params.status !== 'HEPSI') q.set('status', params.status);
    if (params?.severity && params.severity !== 'HEPSI') q.set('severity', params.severity);
    if (params?.finding_type && params.finding_type !== 'HEPSI') q.set('finding_type', params.finding_type);
    if (params?.limit) q.set('limit', String(params.limit));

    const qs = q.toString() ? `?${q.toString()}` : '';
    const res = await fetchWithAuth(`/api/findings${qs}`);
    if (!res.ok) {
      throw new Error(`Bulgular alınamadı (${res.status})`);
    }
    return res.json();
  },

  async runAuditAnalysis(): Promise<AuditRunResponse> {
    const res = await fetchWithAuth('/api/analysis/run', {
      method: 'POST',
    });
    if (!res.ok) {
      throw new Error(`Denetim analizi çalıştırılamadı (${res.status})`);
    }
    return res.json();
  },

  async updateFindingStatus(
    id: number,
    status: string,
    notes?: string
  ): Promise<FindingItem> {
    const res = await fetchWithAuth(`/api/findings/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, resolution_notes: notes }),
    });
    if (!res.ok) {
      throw new Error(`Bulgu durumu güncellenemedi (${res.status})`);
    }
    return res.json();
  },

  async checkCompliance(req: ComplianceCheckRequest): Promise<ComplianceCheckResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    const sessionLlm = getLlmSessionConfig();
    if (sessionLlm?.provider && sessionLlm?.key) {
      headers['X-LLM-Provider'] = sessionLlm.provider;
      headers['X-LLM-Key'] = sessionLlm.key;
    }

    const res = await fetchWithAuth('/api/compliance/check', {
      method: 'POST',
      headers,
      body: JSON.stringify(req),
    });

    if (!res.ok) {
      let errMsg = `Uygunluk denetimi başarısız (${res.status})`;
      try {
        const j = await res.json();
        if (j.detail) errMsg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        // ignore
      }
      throw new Error(errMsg);
    }
    return res.json();
  },

  async getImpactAnalysis(code: string): Promise<ImpactAnalysisResponse> {
    const res = await fetchWithAuth(`/api/documents/${encodeURIComponent(code)}/impact`);
    if (!res.ok) {
      throw new Error(`Etki analizi alınamadı (${res.status}): ${code}`);
    }
    return res.json();
  },
};
