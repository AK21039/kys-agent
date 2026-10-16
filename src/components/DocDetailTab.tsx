import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import { DocumentDetail } from '../types/kys';
import {
  ArrowLeft,
  Calendar,
  AlertCircle,
  FileText,
  Link2,
  FileCheck,
  Image as ImageIcon,
} from 'lucide-react';

interface DocDetailTabProps {
  code: string;
  onOpenDoc: (code: string) => void;
  onClose: () => void;
}

export const DocDetailTab: React.FC<DocDetailTabProps> = ({ code, onOpenDoc, onClose }) => {
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // PDF Preview State
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState<boolean>(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPreviewPage(null);
    setImageUrl(null);
    try {
      const data = await kysApi.getDocument(code);
      setDetail(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Doküman ayrıntısı alınamadı');
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const loadPageImage = async (pageNum: number) => {
    setPreviewPage(pageNum);
    setImageLoading(true);
    setImageError(null);
    try {
      const url = await kysApi.getPageImageUrl(code, pageNum);
      setImageUrl(url);
    } catch (err: unknown) {
      setImageError(err instanceof Error ? err.message : 'Sayfa görüntüsü yüklenemedi');
    } finally {
      setImageLoading(false);
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <button type="button" className="icon-btn" onClick={onClose}>
          <ArrowLeft size={16} />
          <span>Doküman Listesine Dön</span>
        </button>
      </div>

      {loading && (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Doküman ayrıntıları yükleniyor: <strong>{code}</strong>...
        </div>
      )}

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertCircle size={18} />
            <span>Doküman Yüklenemedi</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {detail && (
        <>
          {/* Header Card */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                  <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700 }}>{detail.code}</h2>
                  <span className="badge badge-gray">Rev: {detail.revision || '00'}</span>
                  <span className="badge badge-info">{detail.doc_type}</span>
                  <span className={`badge ${detail.status === 'YURURLUKTE' ? 'badge-ok' : 'badge-warn'}`}>
                    {detail.status}
                  </span>
                </div>
                <h3 style={{ margin: '4px 0 10px', fontSize: '16px', color: 'var(--text)', fontWeight: 600 }}>
                  {detail.title}
                </h3>
              </div>

              {detail.page_count && detail.page_count > 0 && (
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                    {detail.page_count} Sayfa
                  </span>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => loadPageImage(1)}
                  >
                    <ImageIcon size={14} />
                    <span>Sayfaları Önizle</span>
                  </button>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 18, fontSize: '13px', color: 'var(--text-muted)', flexWrap: 'wrap', borderTop: '1px solid var(--line)', paddingTop: 10, marginTop: 10 }}>
              {detail.owner_unit && (
                <div>
                  <strong>Sorumlu Birim:</strong> {detail.owner_unit}
                </div>
              )}
              {detail.revision_date && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Calendar size={13} />
                  <span><strong>Rev. Tarihi:</strong> {detail.revision_date}</span>
                </div>
              )}
              {detail.effective_date && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Calendar size={13} />
                  <span><strong>Yürürlük Tarihi:</strong> {detail.effective_date}</span>
                </div>
              )}
            </div>

            {detail.summary && (
              <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--panel-hover)', borderRadius: 'var(--radius)', fontSize: '13.5px' }}>
                <strong style={{ display: 'block', marginBottom: 4, color: 'var(--text-muted)', fontSize: '12px' }}>ÖZET</strong>
                {detail.summary}
              </div>
            )}
          </div>

          {/* Sayfa Önizleme Bölümü (varsa) */}
          {previewPage !== null && (
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ImageIcon size={18} color="var(--accent)" />
                  <h3 style={{ margin: 0, fontSize: '15px' }}>
                    Doküman Sayfa Görüntüsü (Sayfa {previewPage} / {detail.page_count || '?'})
                  </h3>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {Array.from({ length: detail.page_count || 1 }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      type="button"
                      className={`icon-btn ${previewPage === p ? 'active' : ''}`}
                      onClick={() => loadPageImage(p)}
                      style={{ padding: '3px 8px', fontSize: '12px' }}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => {
                      setPreviewPage(null);
                      setImageUrl(null);
                    }}
                    style={{ padding: '3px 8px', fontSize: '12px' }}
                  >
                    Kapat
                  </button>
                </div>
              </div>

              {imageLoading && (
                <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)' }}>
                  Sayfa görüntüsü alınıyor...
                </div>
              )}

              {imageError && (
                <div style={{ color: 'var(--danger)', fontSize: '13px', padding: 10 }}>
                  {imageError}
                </div>
              )}

              {imageUrl && !imageLoading && (
                <div className="pdf-image-container">
                  <img src={imageUrl} alt={`${code} - Sayfa ${previewPage}`} />
                </div>
              )}
            </div>
          )}

          {/* Atıflar Grid (Referanslar & Referans Verenler) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
            {/* References made by this doc */}
            <div className="card" style={{ margin: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Link2 size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Atıf Yaptığı Dokümanlar ({detail.references?.length || 0})
                </h4>
              </div>

              {(!detail.references || detail.references.length === 0) ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümandan başka bir dokümana atıf bulunmuyor.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.references.map((r, idx) => {
                    const target = r.target_code || r.ref_code;
                    return (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 8px',
                          borderRadius: '4px',
                          border: '1px solid var(--line)',
                          fontSize: '13px',
                        }}
                      >
                        <span
                          className="ref-link"
                          onClick={() => onOpenDoc(target)}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                        >
                          <FileText size={13} />
                          {target}
                        </span>
                        {r.target_title && (
                          <span style={{ color: 'var(--text-muted)', fontSize: '12px', maxWidth: '60%', textAlign: 'right' }} title={r.target_title}>
                            {r.target_title}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Referenced by other docs */}
            <div className="card" style={{ margin: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <FileCheck size={16} color="var(--ok)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Bu Dokümana Atıf Yapanlar ({detail.referenced_by?.length || 0})
                </h4>
              </div>

              {(!detail.referenced_by || detail.referenced_by.length === 0) ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümana atıfta bulunan başka bir doküman tespit edilmedi.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {detail.referenced_by.map((r, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '6px 8px',
                        borderRadius: '4px',
                        border: '1px solid var(--line)',
                        fontSize: '13px',
                      }}
                    >
                      <span
                        className="ref-link"
                        onClick={() => onOpenDoc(r.code)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                      >
                        <FileText size={13} />
                        {r.code}
                      </span>
                      {r.title && (
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px', maxWidth: '60%', textAlign: 'right' }} title={r.title}>
                          {r.title}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Sections List */}
          <div className="card">
            <h3 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 600 }}>
              Doküman Maddeleri ve Bölümleri ({detail.sections?.length || 0})
            </h3>

            {(!detail.sections || detail.sections.length === 0) ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                Dokümana ait ayrıştırılmış madde bulunamadı.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {detail.sections.map((sec, idx) => (
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
                      {sec.clause_no && (
                        <span className="badge badge-info" style={{ fontWeight: 700 }}>
                          Md. {sec.clause_no}
                        </span>
                      )}
                      {sec.page && (
                        <button
                          type="button"
                          className="badge badge-gray"
                          onClick={() => loadPageImage(sec.page!)}
                          style={{ cursor: 'pointer', border: '1px solid var(--line)' }}
                          title="Sayfa görüntüsünü aç"
                        >
                          <ImageIcon size={11} style={{ marginRight: 2 }} />
                          Sayfa {sec.page}
                        </button>
                      )}
                      {sec.heading && (
                        <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                          {sec.heading}
                        </span>
                      )}
                      {sec.heading_path && sec.heading_path !== sec.heading && (
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          ({sec.heading_path})
                        </span>
                      )}
                    </div>

                    <div
                      style={{
                        fontSize: '13.5px',
                        lineHeight: 1.6,
                        whiteSpace: 'pre-wrap',
                        color: 'var(--text)',
                      }}
                    >
                      {sec.text}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
};
