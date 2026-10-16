import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import { ReferencesResponse } from '../types/kys';
import { AlertTriangle, RefreshCw, AlertCircle, FileText, CheckCircle2 } from 'lucide-react';

interface RefsTabProps {
  onOpenDoc: (code: string) => void;
}

export const RefsTab: React.FC<RefsTabProps> = ({ onOpenDoc }) => {
  const [data, setData] = useState<ReferencesResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRefs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await kysApi.getReferences();
      setData(resp);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Eksik atıflar alınamadı');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRefs();
  }, [fetchRefs]);

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={18} color="var(--warn)" />
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Çözülmemiş ve Eksik Doküman Atıfları</h2>
          </div>
          <button type="button" className="icon-btn" onClick={fetchRefs} disabled={loading}>
            <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            <span>Yenile</span>
          </button>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
          Yürürlükteki dokümanlarda atıfta bulunulan fakat KYS sisteminde henüz kaydı veya metni bulunmayan doküman kodları.
        </p>
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

      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Eksik atıf kayıtları taranıyor...
        </div>
      ) : data ? (
        <>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: '15px' }}>
                Eksik Dokümanlar ({data.missing_documents?.length || 0})
              </h3>
            </div>

            {(!data.missing_documents || data.missing_documents.length === 0) ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ok)', padding: '16px 0' }}>
                <CheckCircle2 size={18} />
                <span>Harika! Çözülmemiş hiçbir doküman atfı tespit edilmedi.</span>
              </div>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Eksik / Tanımsız Kod</th>
                      <th>Atıf Yapan Dokümanlar</th>
                      <th>Kaynak Sayısı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.missing_documents.map((item, idx) => (
                      <tr key={idx}>
                        <td>
                          <span style={{ fontWeight: 700, color: 'var(--warn)' }}>
                            {item.code}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            {item.referenced_from?.map((fromCode) => (
                              <span
                                key={fromCode}
                                className="ref-link"
                                onClick={() => onOpenDoc(fromCode)}
                                style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: '13px' }}
                              >
                                <FileText size={12} />
                                {fromCode}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td>
                          <span className="badge badge-gray">
                            {item.referenced_from?.length || 0} doküman
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {data.probably_not_documents && data.probably_not_documents.length > 0 && (
            <div className="card">
              <h4 style={{ margin: '0 0 8px 0', fontSize: '14px', color: 'var(--text-muted)' }}>
                Doküman Kodu Olmadığı Değerlendirilen Diğer Referanslar ({data.probably_not_documents.length})
              </h4>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {data.probably_not_documents.map((pnd, idx) => (
                  <span key={idx} className="badge badge-gray" style={{ fontSize: '12px' }}>
                    {pnd}
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
};
