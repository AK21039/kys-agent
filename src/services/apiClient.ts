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
} from '../types/kys';

const STORAGE_KEY_API_BASE = 'kys_api_base';
const STORAGE_KEY_TOKEN = 'kys_token';

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

export const getApiConfig = () => {
  let apiBase = '';
  let token = '';
  try {
    apiBase = localStorage.getItem(STORAGE_KEY_API_BASE) || '';
    token = localStorage.getItem(STORAGE_KEY_TOKEN) || '';
  } catch {
    // ignore
  }
  return { apiBase, token };
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

  async ask(question: string): Promise<AskResponse> {
    const res = await fetchWithAuth('/api/ask', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) {
      throw new Error(`Soru yanıtlama başarısız (${res.status})`);
    }
    return res.json();
  },
};
