import React, { useState, useEffect, useRef, useCallback } from 'react';
import mermaid from 'mermaid';
import { kysApi } from '../services/apiClient';
import { ProcessSummary, ProcessDetail, ProcessStep } from '../types/kys';
import {
  GitBranch,
  RefreshCw,
  AlertCircle,
  FileText,
  UserCheck,
  HelpCircle,
  Image as ImageIcon,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from 'lucide-react';

interface ProcessesTabProps {
  onOpenDoc: (code: string) => void;
}

export const ProcessesTab: React.FC<ProcessesTabProps> = ({ onOpenDoc }) => {
  const [processes, setProcesses] = useState<ProcessSummary[]>([]);
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [processDetail, setProcessDetail] = useState<ProcessDetail | null>(null);

  const [loadingList, setLoadingList] = useState<boolean>(true);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Selected Step & Page
  const [selectedStep, setSelectedStep] = useState<ProcessStep | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageImageUrl, setPageImageUrl] = useState<string | null>(null);
  const [pageImageLoading, setPageImageLoading] = useState<boolean>(false);
  const [pageImageError, setPageImageError] = useState<string | null>(null);

  // Mermaid SVG
  const [mermaidSvg, setMermaidSvg] = useState<string>('');
  const mermaidContainerRef = useRef<HTMLDivElement>(null);
  const [diagramZoom, setDiagramZoom] = useState<number>(1);

  // Initialize Mermaid
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'default',
      securityLevel: 'loose',
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
        curve: 'basis',
      },
    });
  }, []);

  const fetchProcesses = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      const data = await kysApi.getProcesses();
      setProcesses(data);
      if (data.length > 0 && !selectedCode) {
        setSelectedCode(data[0].code);
      }
    } catch (err: unknown) {
      setListError(err instanceof Error ? err.message : 'Süreç listesi alınamadı');
    } finally {
      setLoadingList(false);
    }
  }, [selectedCode]);

  useEffect(() => {
    fetchProcesses();
  }, [fetchProcesses]);

  // Fetch single process detail
  const fetchProcessDetail = useCallback(async (code: string) => {
    setLoadingDetail(true);
    setDetailError(null);
    setSelectedStep(null);
    setMermaidSvg('');
    setPageImageUrl(null);
    try {
      const data = await kysApi.getProcess(code);
      setProcessDetail(data);

      // Render Mermaid if provided
      if (data.mermaid && data.mermaid.trim()) {
        try {
          const uniqueId = `mermaid_${code.replace(/[^a-zA-Z0-9]/g, '_')}_${Date.now()}`;
          const { svg } = await mermaid.render(uniqueId, data.mermaid.trim());
          setMermaidSvg(svg);
        } catch (mErr) {
          console.warn('Mermaid rendering failed', mErr);
          setMermaidSvg('');
        }
      }

      // If process has pages, default to page 1
      if (data.page_count && data.page_count > 0) {
        setCurrentPage(1);
        loadPageImage(code, 1);
      }
    } catch (err: unknown) {
      setDetailError(err instanceof Error ? err.message : 'Süreç ayrıntısı yüklenemedi');
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCode) {
      fetchProcessDetail(selectedCode);
    }
  }, [selectedCode, fetchProcessDetail]);

  const loadPageImage = async (code: string, pageNum: number) => {
    setCurrentPage(pageNum);
    setPageImageLoading(true);
    setPageImageError(null);
    try {
      const url = await kysApi.getPageImageUrl(code, pageNum);
      setPageImageUrl(url);
    } catch (err: unknown) {
      setPageImageError(err instanceof Error ? err.message : `Sayfa ${pageNum} yüklenemedi`);
    } finally {
      setPageImageLoading(false);
    }
  };

  const handleStepClick = (step: ProcessStep) => {
    setSelectedStep(step);
    if (step.page && selectedCode && step.page !== currentPage) {
      loadPageImage(selectedCode, step.page);
    }
  };

  return (
    <div>
      {/* Top Selector Card */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <GitBranch size={18} color="var(--accent)" />
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>KYS Süreç Envanteri ve Akış Şemaları</h2>
          </div>
          <button type="button" className="icon-btn" onClick={fetchProcesses} disabled={loadingList}>
            <RefreshCw size={14} style={{ animation: loadingList ? 'spin 1s linear infinite' : 'none' }} />
            <span>Süreçleri Yenile</span>
          </button>
        </div>

        {listError && (
          <div style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: 10 }}>
            {listError}
          </div>
        )}

        {/* Process Pills / Selector */}
        {loadingList ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Süreçler taranıyor...</div>
        ) : (
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 6, scrollbarWidth: 'thin' }}>
            {processes.map((proc) => {
              const isSelected = proc.code === selectedCode;
              return (
                <button
                  key={proc.code}
                  type="button"
                  onClick={() => setSelectedCode(proc.code)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '8px 12px',
                    borderRadius: 'var(--radius)',
                    border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--line)'}`,
                    backgroundColor: isSelected ? 'var(--accent-soft)' : 'var(--panel)',
                    color: isSelected ? 'var(--accent)' : 'var(--text)',
                    cursor: 'pointer',
                    minWidth: 160,
                    textAlign: 'left',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: '13px' }}>{proc.code}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 180 }}>
                    {proc.name}
                  </div>
                  <div style={{ fontSize: '11px', marginTop: 4, opacity: 0.8 }}>
                    {proc.step_count} Adım
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {detailError && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertCircle size={18} />
            <span>Süreç Yüklenemedi</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{detailError}</p>
        </div>
      )}

      {loadingDetail && (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Süreç ayrıntıları ve şeması yükleniyor: <strong>{selectedCode}</strong>...
        </div>
      )}

      {processDetail && !loadingDetail && (
        <>
          {/* Header Info */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{processDetail.code}</h3>
                  <span className="badge badge-info">{processDetail.steps?.length || 0} Adım</span>
                  {processDetail.page_count > 0 && (
                    <span className="badge badge-gray">{processDetail.page_count} PDF Sayfası</span>
                  )}
                </div>
                <div style={{ fontSize: '15px', color: 'var(--text-muted)', marginTop: 4, fontWeight: 500 }}>
                  {processDetail.name}
                </div>
              </div>

              <div>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => onOpenDoc(processDetail.code)}
                  title="Doküman Ayrıntısına Git"
                >
                  <FileText size={15} />
                  <span>Doküman Metnine Git</span>
                </button>
              </div>
            </div>
          </div>

          {/* Main 2-column layout: Left: Mermaid Diagram / Steps; Right: Page Image / Quote */}
          <div className="process-layout">
            {/* Left Column: Mermaid Diagram & Steps List */}
            <div className="diagram-panel">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <h4 style={{ margin: 0, fontSize: '14.5px', fontWeight: 600 }}>
                  Süreç Akış Şeması
                </h4>
                {mermaidSvg && (
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      type="button"
                      className="icon-btn"
                      style={{ padding: '3px 6px' }}
                      onClick={() => setDiagramZoom((z) => Math.min(z + 0.2, 2.5))}
                      title="Yakınlaştır"
                    >
                      <ZoomIn size={14} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      style={{ padding: '3px 6px' }}
                      onClick={() => setDiagramZoom((z) => Math.max(z - 0.2, 0.5))}
                      title="Uzaklaştır"
                    >
                      <ZoomOut size={14} />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      style={{ padding: '3px 6px' }}
                      onClick={() => setDiagramZoom(1)}
                      title="Sıfırla"
                    >
                      <Maximize2 size={14} />
                    </button>
                  </div>
                )}
              </div>

              {mermaidSvg ? (
                <div
                  ref={mermaidContainerRef}
                  className="diagram-svg-container"
                  style={{
                    transform: `scale(${diagramZoom})`,
                    transformOrigin: 'top center',
                    transition: 'transform 0.15s ease',
                  }}
                  dangerouslySetInnerHTML={{ __html: mermaidSvg }}
                />
              ) : (
                <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                  Bu süreç için oluşturulmuş Mermaid akış şeması bulunamadı.
                </div>
              )}

              {/* Steps Table/List */}
              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', fontWeight: 600 }}>
                  Süreç Adımları (Adıma tıklayınca kanıt alıntısı ve sayfa açılır)
                </h4>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 380, overflowY: 'auto' }}>
                  {processDetail.steps?.map((step) => {
                    const isSelected = selectedStep?.seq === step.seq;
                    return (
                      <div
                        key={step.seq}
                        onClick={() => handleStepClick(step)}
                        style={{
                          padding: '8px 10px',
                          borderRadius: 'var(--radius)',
                          border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--line)'}`,
                          backgroundColor: isSelected ? 'var(--accent-soft)' : 'var(--panel)',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span
                              style={{
                                width: 22,
                                height: 22,
                                borderRadius: '50%',
                                background: isSelected ? 'var(--accent)' : 'var(--line)',
                                color: isSelected ? '#fff' : 'var(--text)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '11px',
                                fontWeight: 700,
                              }}
                            >
                              {step.seq}
                            </span>
                            <span style={{ fontWeight: 600, fontSize: '13px' }}>{step.name}</span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {step.page && (
                              <span className="badge badge-gray" style={{ fontSize: '11px' }}>
                                S. {step.page}
                              </span>
                            )}
                            <ChevronRight size={14} color="var(--text-muted)" />
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: 12, fontSize: '12px', color: 'var(--text-muted)', marginTop: 4, marginLeft: 28 }}>
                          {step.responsible && (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                              <UserCheck size={12} color="var(--accent)" />
                              {step.responsible}
                            </span>
                          )}
                          {step.decision && (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: 'var(--warn)' }}>
                              <HelpCircle size={12} />
                              {step.decision}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Right Column: Selected Step Detail & PDF Page Preview */}
            <div className="preview-panel">
              {/* Selected Step Info */}
              <div style={{ marginBottom: 16 }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14.5px', fontWeight: 600 }}>
                  {selectedStep ? `Adım ${selectedStep.seq}: ${selectedStep.name}` : 'Adım Detayı'}
                </h4>

                {selectedStep ? (
                  <div style={{ backgroundColor: 'var(--panel-hover)', padding: '12px', borderRadius: 'var(--radius)', border: '1px solid var(--line)' }}>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
                      {selectedStep.responsible && (
                        <div>
                          <strong style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>SORUMLU</strong>
                          <span style={{ fontSize: '13px', fontWeight: 600 }}>{selectedStep.responsible}</span>
                        </div>
                      )}
                      {selectedStep.decision && (
                        <div>
                          <strong style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>KARAR / KOŞUL</strong>
                          <span style={{ fontSize: '13px', color: 'var(--warn)', fontWeight: 600 }}>{selectedStep.decision}</span>
                        </div>
                      )}
                      {selectedStep.next_steps && selectedStep.next_steps.length > 0 && (
                        <div>
                          <strong style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>SONRAKİ ADIMLAR</strong>
                          <span style={{ fontSize: '13px' }}>{selectedStep.next_steps.join(', ')}</span>
                        </div>
                      )}
                    </div>

                    {selectedStep.quote ? (
                      <div className="quote-box" style={{ margin: 0 }}>
                        <strong style={{ display: 'block', fontSize: '11px', color: 'var(--accent)', marginBottom: 2 }}>
                          DOKÜMAN BİREBİR KANIT ALINTISI:
                        </strong>
                        "{selectedStep.quote}"
                      </div>
                    ) : (
                      <div style={{ fontSize: '12.5px', color: 'var(--text-muted)' }}>
                        Bu adım için doğrudan metin alıntısı bulunamadı.
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                    Sol listeden veya şemadan bir adıma tıklayarak kanıt alıntısını ve sayfasını inceleyebilirsiniz.
                  </p>
                )}
              </div>

              {/* PDF Sayfa Görüntüsü */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 6 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ImageIcon size={16} color="var(--accent)" />
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>
                      Sayfa Görüntüsü {processDetail.page_count > 0 ? `(${currentPage} / ${processDetail.page_count})` : ''}
                    </h4>
                  </div>

                  {processDetail.page_count > 0 && (
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {Array.from({ length: processDetail.page_count }, (_, i) => i + 1).map((p) => (
                        <button
                          key={p}
                          type="button"
                          className={`icon-btn ${currentPage === p ? 'active' : ''}`}
                          style={{
                            padding: '2px 7px',
                            fontSize: '11.5px',
                            backgroundColor: currentPage === p ? 'var(--accent)' : undefined,
                            color: currentPage === p ? '#fff' : undefined,
                          }}
                          onClick={() => selectedCode && loadPageImage(selectedCode, p)}
                        >
                          {p}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {pageImageLoading && (
                  <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                    Sayfa {currentPage} görüntüsü yükleniyor...
                  </div>
                )}

                {pageImageError && (
                  <div style={{ color: 'var(--danger)', fontSize: '12.5px', padding: 8 }}>
                    {pageImageError}
                  </div>
                )}

                {pageImageUrl && !pageImageLoading && (
                  <div className="pdf-image-container">
                    <img
                      src={pageImageUrl}
                      alt={`${processDetail.code} - Sayfa ${currentPage}`}
                      style={{ maxHeight: 520, objectFit: 'contain' }}
                    />
                  </div>
                )}

                {!pageImageUrl && !pageImageLoading && !pageImageError && (
                  <div style={{ padding: '30px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                    Sayfa önizlemesi bulunamadı.
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
