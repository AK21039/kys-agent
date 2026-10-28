import React, { useState } from 'react';
import { kysApi } from '../services/apiClient';
import { SearchResult } from '../types/kys';
import { Search, FileText, AlertCircle } from 'lucide-react';

interface SearchTabProps {
  onOpenDoc: (code: string) => void;
}

export const SearchTab: React.FC<SearchTabProps> = ({ onOpenDoc }) => {
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);

    try {
      const data = await kysApi.search(q, 20);
      setResults(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Arama sırasında hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="card">
        <h2 style={{ margin: '0 0 10px 0', fontSize: '16px', fontWeight: 600 }}>
          KYS Madde ve Bölüm Arama
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
          Tüm prosedür, talimat, form ve politika maddelerinde sunucu tabanlı Türkçe arama yapın.
        </p>

        <form className="search-form" onSubmit={handleSearch}>
          <input
            type="text"
            placeholder="Anahtar kelime, kavram veya madde ara... (Örn: yetki, satın alma, onay)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="primary" disabled={loading || !query.trim()}>
            {loading ? (
              'Aranıyor...'
            ) : (
              <>
                <Search size={16} />
                <span>Ara</span>
              </>
            )}
          </button>
        </form>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertCircle size={18} />
            <span>Arama Hatası</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {results && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: '15px' }}>
              Sonuçlar ({results.length})
            </h3>
            {results.length >= 20 && (
              <span className="badge badge-gray">İlk 20 kayıt gösteriliyor</span>
            )}
          </div>

          {results.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '13.5px', margin: 0 }}>
              "{query}" ile eşleşen madde bulunamadı.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {results.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    border: '1px solid var(--line)',
                    borderRadius: 'var(--radius)',
                    padding: '12px 14px',
                    backgroundColor: 'var(--panel)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                    <span
                      className="ref-link"
                      onClick={() => onOpenDoc(item.code)}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                    >
                      <FileText size={14} />
                      {item.code}
                    </span>

                    {item.revision && (
                      <span className="badge badge-gray">Rev: {item.revision}</span>
                    )}

                    {item.clause_no && (
                      <span className="badge badge-info">Md. {item.clause_no}</span>
                    )}

                    {item.page && (
                      <span className="badge badge-gray">Sayfa {item.page}</span>
                    )}

                    {item.heading && (
                      <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
                        {item.heading}
                      </span>
                    )}
                  </div>

                  {item.title && (
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: 6 }}>
                      {item.title}
                    </div>
                  )}

                  <div
                    style={{
                      fontSize: '13.5px',
                      lineHeight: 1.5,
                      color: 'var(--text)',
                      backgroundColor: 'var(--panel-hover)',
                      padding: '8px 10px',
                      borderRadius: '4px',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    {item.text}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
