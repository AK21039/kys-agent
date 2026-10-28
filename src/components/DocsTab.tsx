import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import { DocumentSummary } from '../types/kys';
import { FileText, Filter, Search, RefreshCw, AlertCircle, Calendar } from 'lucide-react';

interface DocsTabProps {
  onOpenDoc: (code: string) => void;
  availableTypes?: string[];
}

const COMMON_DOC_TYPES = [
  'HEPSI',
  'PROSEDUR',
  'TALIMAT',
  'FORM',
  'EL_KITABI',
  'POLITIKA',
  'PROSES_KARTI',
  'GOREV_TANIMI',
  'YETKI_MATRISI',
  'LISTE',
  'PLAN',
  'DIS_KAYNAK',
];

export const DocsTab: React.FC<DocsTabProps> = ({ onOpenDoc, availableTypes = [] }) => {
  const [selectedType, setSelectedType] = useState<string>('HEPSI');
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kysApi.getDocuments(selectedType === 'HEPSI' ? undefined : selectedType);
      setDocs(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Dokümanlar yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [selectedType]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs]);

  // Combine known types with availableTypes
  const typeOptions = Array.from(new Set([...COMMON_DOC_TYPES, ...availableTypes]));

  const filteredDocs = docs.filter((d) => {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return (
      d.code?.toLowerCase().includes(q) ||
      d.title?.toLowerCase().includes(q) ||
      d.owner_unit?.toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <FileText size={18} color="var(--accent)" />
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>KYS Doküman Kataloğu</h2>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={fetchDocs}
            disabled={loading}
          >
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            <span>Yenile</span>
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 1fr) 2fr', gap: 10 }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
              <Filter size={12} style={{ display: 'inline', marginRight: 4 }} />
              Doküman Tipi Filtresi
            </label>
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
            >
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t === 'HEPSI' ? 'Tüm Tipler' : t}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
              <Search size={12} style={{ display: 'inline', marginRight: 4 }} />
              Kod veya Başlıkta Filtrele
            </label>
            <input
              type="text"
              placeholder="Doküman kodu veya adında filtrele..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertCircle size={18} />
            <span>Hata</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: '15px' }}>
            Listelenen Dokümanlar ({filteredDocs.length})
          </h3>
        </div>

        {loading ? (
          <div style={{ padding: '30px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            Dokümanlar yükleniyor...
          </div>
        ) : filteredDocs.length === 0 ? (
          <div style={{ padding: '30px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
            Kriterlere uygun doküman bulunamadı.
          </div>
        ) : (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Doküman Kodu</th>
                  <th>Rev.</th>
                  <th>Başlık</th>
                  <th>Tip</th>
                  <th>Durum</th>
                  <th>Birim / Tarih</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocs.map((doc) => {
                  const isYururlukte = doc.status === 'YURURLUKTE';
                  return (
                    <tr key={doc.code}>
                      <td>
                        <span
                          className="ref-link"
                          onClick={() => onOpenDoc(doc.code)}
                          style={{ fontWeight: 600 }}
                        >
                          {doc.code}
                        </span>
                      </td>
                      <td>
                        <span className="badge badge-gray">{doc.revision || '00'}</span>
                      </td>
                      <td style={{ fontWeight: 500 }}>
                        {doc.title}
                        {doc.summary && (
                          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 2 }}>
                            {doc.summary}
                          </div>
                        )}
                      </td>
                      <td>
                        <span className="badge badge-info">{doc.doc_type}</span>
                      </td>
                      <td>
                        <span className={`badge ${isYururlukte ? 'badge-ok' : 'badge-warn'}`}>
                          {doc.status}
                        </span>
                      </td>
                      <td style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {doc.owner_unit && <div>{doc.owner_unit}</div>}
                        {doc.revision_date && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                            <Calendar size={12} />
                            {doc.revision_date}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
