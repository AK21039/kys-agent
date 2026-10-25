import React, { useState, useEffect, useRef, useCallback } from 'react';
import mermaid from 'mermaid';
import { kysApi } from '../services/apiClient';
import {
  ProcessSummary,
  ProcessDetail,
  ProcessStep,
  DecisionItem,
  ClauseMatchSuggestion,
} from '../types/kys';
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
  Table,
  Upload,
  Plus,
  Trash2,
  Sparkles,
  Link2,
  X,
} from 'lucide-react';

interface ProcessesTabProps {
  onOpenDoc: (code: string) => void;
}

export const ProcessesTab: React.FC<ProcessesTabProps> = ({ onOpenDoc }) => {
  const [activeTab, setActiveTab] = useState<'flow' | 'raci' | 'import'>('flow');

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

  // RACI Decisions state
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [loadingDecisions, setLoadingDecisions] = useState<boolean>(false);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);

  // New Decision Modal
  const [showDecisionModal, setShowDecisionModal] = useState<boolean>(false);
  const [decisionTopic, setDecisionTopic] = useState<string>('');
  const [decisionMaker, setDecisionMaker] = useState<string>('');
  const [decisionResponsible, setDecisionResponsible] = useState<string>('');
  const [decisionConsulted, setDecisionConsulted] = useState<string>('');
  const [decisionInformed, setDecisionInformed] = useState<string>('');
  const [savingDecision, setSavingDecision] = useState<boolean>(false);

  // Agent 2.1 Matcher state
  const [matchingStepSeq, setMatchingStepSeq] = useState<number | null>(null);
  const [matchSuggestions, setMatchSuggestions] = useState<ClauseMatchSuggestion[]>([]);
  const [loadingMatches, setLoadingMatches] = useState<boolean>(false);
  const [matchError, setMatchError] = useState<string | null>(null);

  // Excel Upload State
  const [uploadMessage, setUploadMessage] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [uploading, setUploading] = useState<boolean>(false);

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

  const fetchDecisions = useCallback(async (code: string) => {
    setLoadingDecisions(true);
    setDecisionsError(null);
    try {
      const data = await kysApi.getDecisions(code);
      setDecisions(data);
    } catch (err: unknown) {
      setDecisionsError(err instanceof Error ? err.message : 'Karar envanteri alınamadı');
    } finally {
      setLoadingDecisions(false);
    }
  }, []);

  useEffect(() => {
    if (selectedCode) {
      fetchProcessDetail(selectedCode);
      if (activeTab === 'raci') {
        fetchDecisions(selectedCode);
      }
    }
  }, [selectedCode, activeTab, fetchProcessDetail, fetchDecisions]);

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

  const handleSaveDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCode || !decisionTopic.trim() || !decisionMaker.trim()) return;

    setSavingDecision(true);
    try {
      const created = await kysApi.createOrUpdateDecision({
        process_code: selectedCode,
        topic: decisionTopic.trim(),
        decision_maker: decisionMaker.trim(),
        responsible: decisionResponsible.trim() || null,
        consulted: decisionConsulted.trim() ? decisionConsulted.split(',').map((s) => s.trim()) : null,
        informed: decisionInformed.trim() ? decisionInformed.split(',').map((s) => s.trim()) : null,
      });
      setDecisions((prev) => [...prev, created]);
      setShowDecisionModal(false);
      setDecisionTopic('');
      setDecisionMaker('');
      setDecisionResponsible('');
      setDecisionConsulted('');
      setDecisionInformed('');
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Karar kaydedilemedi');
    } finally {
      setSavingDecision(false);
    }
  };

  const handleDeleteDecision = async (id: number) => {
    if (!window.confirm('Bu kararı silmek istediğinizden emin misiniz?')) return;
    try {
      await kysApi.deleteDecision(id);
      setDecisions((prev) => prev.filter((d) => d.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Karar silinemedi');
    }
  };

  const handleGetClauseMatches = async (stepSeq: number) => {
    if (!selectedCode) return;
    setMatchingStepSeq(stepSeq);
    setLoadingMatches(true);
    setMatchError(null);
    setMatchSuggestions([]);
    try {
      const res = await kysApi.suggestClauseMatches(selectedCode, stepSeq);
      setMatchSuggestions(res);
    } catch (err: unknown) {
      setMatchError(err instanceof Error ? err.message : 'Madde eşleşme önerileri alınamadı');
    } finally {
      setLoadingMatches(false);
    }
  };

  const handleLinkClause = async (stepSeq: number, docCode: string, clauseNo: string) => {
    if (!selectedCode) return;
    try {
      await kysApi.linkStepClause(selectedCode, stepSeq, docCode, clauseNo);
      alert(`Adım ${stepSeq}, ${docCode} Md. ${clauseNo} maddesine bağlandı.`);
      fetchProcessDetail(selectedCode);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Madde bağlanamadı');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, type: 'process' | 'decision') => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadMessage(null);
    try {
      const res =
        type === 'process'
          ? await kysApi.importProcessExcel(file)
          : await kysApi.importDecisionsExcel(file);
      setUploadMessage({
        type: 'ok',
        text: `İçe aktarma başarılı! Toplam ${res.imported_count} kayıt eklendi/güncellendi.`,
      });
      fetchProcesses();
      if (selectedCode) fetchDecisions(selectedCode);
    } catch (err: unknown) {
      setUploadMessage({
        type: 'err',
        text: err instanceof Error ? err.message : 'Yükleme başarısız',
      });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <div>
      {/* Top Selector Card */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <GitBranch size={20} color="var(--accent)" />
            <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
              KYS Süreç & Karar Stüdyosu (Faz 2)
            </h2>
          </div>
          <button type="button" className="icon-btn" onClick={fetchProcesses} disabled={loadingList}>
            <RefreshCw size={14} style={{ animation: loadingList ? 'spin 1s linear infinite' : 'none' }} />
            <span>Süreçleri Yenile</span>
          </button>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
          Süreç adımları, karar envanteri (RACI matrisi), Excel içe aktarımı ve Ajan 2.1 ile doküman maddelerine otomatik bağlama stüdyosu.
        </p>

        {listError && (
          <div style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: 10 }}>
            {listError}
          </div>
        )}

        {/* Process Selector Pills */}
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

        {/* Sub-tab Navigation */}
        <div style={{ display: 'flex', gap: 8, borderTop: '1px solid var(--line)', paddingTop: 12, marginTop: 12 }}>
          <button
            type="button"
            className={activeTab === 'flow' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('flow')}
            style={{ fontSize: '13px', padding: '6px 14px' }}
          >
            <GitBranch size={14} />
            <span>Akış Şeması & Önizleme</span>
          </button>

          <button
            type="button"
            className={activeTab === 'raci' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('raci')}
            style={{ fontSize: '13px', padding: '6px 14px' }}
          >
            <Table size={14} />
            <span>Karar Envanteri (RACI)</span>
          </button>

          <button
            type="button"
            className={activeTab === 'import' ? 'primary' : 'secondary'}
            onClick={() => setActiveTab('import')}
            style={{ fontSize: '13px', padding: '6px 14px' }}
          >
            <Upload size={14} />
            <span>Excel İçe Aktar & Eşleştir</span>
          </button>
        </div>
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

      {/* TAB 1: FLOW DIAGRAM & PREVIEW */}
      {activeTab === 'flow' && processDetail && !loadingDetail && (
        <>
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

          <div className="process-layout">
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

              <div style={{ marginTop: 16 }}>
                <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', fontWeight: 600 }}>
                  Süreç Adımları (Tıklayınca kanıt alıntısı ve sayfa açılır)
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

            <div className="preview-panel">
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
              </div>
            </div>
          </div>
        </>
      )}

      {/* TAB 2: RACI DECISION MATRIX */}
      {activeTab === 'raci' && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700 }}>
                Karar Envanteri & RACI Yetki Matrisi ({selectedCode || 'Tümü'})
              </h3>
              <p style={{ margin: '4px 0 0', fontSize: '12.5px', color: 'var(--text-muted)' }}>
                <strong>A (Accountable):</strong> Karar Sahibi / Onaylayan · <strong>R (Responsible):</strong> Yürüten / Hazırlayan · <strong>C (Consulted):</strong> Danışılan · <strong>I (Informed):</strong> Bilgilendirilen
              </p>
            </div>

            <button
              type="button"
              className="primary"
              onClick={() => setShowDecisionModal(true)}
              style={{ fontSize: '13px', padding: '6px 12px' }}
            >
              <Plus size={14} />
              <span>Yeni Karar Ekle</span>
            </button>
          </div>

          {decisionsError && (
            <div style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: 10 }}>
              {decisionsError}
            </div>
          )}

          {loadingDecisions ? (
            <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)' }}>
              Karar envanteri yükleniyor...
            </div>
          ) : decisions.length === 0 ? (
            <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)' }}>
              Bu süreç için henüz kayıtlı bir karar envanteri bulunmuyor. Yeni karar ekleyebilir veya Excel'den içe aktarabilirsiniz.
            </div>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Karar Konusu</th>
                    <th>Karar Sahibi (A)</th>
                    <th>Yürüten (R)</th>
                    <th>Danışılan (C)</th>
                    <th>Bilgilendirilen (I)</th>
                    <th>Dayanak Kural / Madde</th>
                    <th>İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((d) => (
                    <tr key={d.id}>
                      <td style={{ fontWeight: 600 }}>{d.topic}</td>
                      <td>
                        <span className="badge badge-info" style={{ fontWeight: 700 }}>
                          {d.decision_maker}
                        </span>
                      </td>
                      <td>{d.responsible || '-'}</td>
                      <td>
                        {Array.isArray(d.consulted)
                          ? d.consulted.join(', ')
                          : d.consulted || '-'}
                      </td>
                      <td>
                        {Array.isArray(d.informed)
                          ? d.informed.join(', ')
                          : d.informed || '-'}
                      </td>
                      <td style={{ fontSize: '12px' }}>
                        {d.source_document ? (
                          <span
                            className="ref-link"
                            onClick={() => onOpenDoc(d.source_document!)}
                          >
                            {d.source_document} {d.source_clause ? `Md. ${d.source_clause}` : ''}
                          </span>
                        ) : d.rule_summary ? (
                          <span>{d.rule_summary}</span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>-</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => handleDeleteDecision(d.id)}
                          style={{ color: 'var(--danger)', padding: '2px 6px' }}
                          title="Kararı Sil"
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: EXCEL IMPORT & CLAUSE MATCHER */}
      {activeTab === 'import' && (
        <div>
          {uploadMessage && (
            <div
              className="card"
              style={{
                backgroundColor: uploadMessage.type === 'ok' ? 'var(--ok-soft)' : 'var(--danger-soft)',
                border: `1px solid ${uploadMessage.type === 'ok' ? 'var(--ok-border)' : 'var(--danger-border)'}`,
                color: uploadMessage.type === 'ok' ? 'var(--ok)' : 'var(--danger)',
                padding: '12px 14px',
                marginBottom: 14,
              }}
            >
              {uploadMessage.text}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
            {/* Süreç Adımları İçe Aktarma */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Upload size={18} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '15px' }}>Süreç Adımları Excel İçe Aktar</h4>
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '12.5px', margin: '0 0 12px 0' }}>
                Excel şablonu: Sütunlar: <code>seq</code>, <code>name</code>, <code>responsible</code>, <code>decision</code>, <code>next_steps</code>.
              </p>

              <label className="secondary" style={{ display: 'inline-flex', cursor: 'pointer' }}>
                <span>{uploading ? 'Yükleniyor...' : 'Excel Dosyası Seç (.xlsx)'}</span>
                <input
                  type="file"
                  accept=".xlsx, .xls"
                  onChange={(e) => handleFileUpload(e, 'process')}
                  disabled={uploading}
                  style={{ display: 'none' }}
                />
              </label>
            </div>

            {/* Karar Envanteri İçe Aktarma */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <Table size={18} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '15px' }}>Karar Envanteri (RACI) Excel İçe Aktar</h4>
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '12.5px', margin: '0 0 12px 0' }}>
                Excel şablonu: Sütunlar: <code>process_code</code>, <code>topic</code>, <code>decision_maker</code>, <code>responsible</code>, <code>consulted</code>, <code>informed</code>.
              </p>

              <label className="secondary" style={{ display: 'inline-flex', cursor: 'pointer' }}>
                <span>{uploading ? 'Yükleniyor...' : 'Excel Dosyası Seç (.xlsx)'}</span>
                <input
                  type="file"
                  accept=".xlsx, .xls"
                  onChange={(e) => handleFileUpload(e, 'decision')}
                  disabled={uploading}
                  style={{ display: 'none' }}
                />
              </label>
            </div>
          </div>

          {/* Ajan 2.1 Süreç Eşleştirici */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Sparkles size={18} color="var(--accent)" />
              <h3 style={{ margin: 0, fontSize: '16px' }}>
                Ajan 2.1: Süreç Adımını Doküman Maddesiyle Eşleştirme Önerisi
              </h3>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
              Seçili sürecin adımlarına tıklayarak FTS ve semantik arama ile en uygun KYS doküman maddesini tespit edin ve tek tıkla bağlayın.
            </p>

            {processDetail && (
              <div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
                  {processDetail.steps?.map((step) => (
                    <button
                      key={step.seq}
                      type="button"
                      className={`icon-btn ${matchingStepSeq === step.seq ? 'active' : ''}`}
                      onClick={() => handleGetClauseMatches(step.seq)}
                      disabled={loadingMatches}
                    >
                      <span>{step.seq}. {step.name}</span>
                    </button>
                  ))}
                </div>

                {loadingMatches && (
                  <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                    Ajan 2.1 doküman maddelerini inceliyor...
                  </div>
                )}

                {matchError && (
                  <div style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: 10 }}>
                    {matchError}
                  </div>
                )}

                {matchSuggestions.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>
                      Önerilen Doküman Maddeleri:
                    </h4>

                    {matchSuggestions.map((m, idx) => (
                      <div
                        key={idx}
                        style={{
                          border: '1px solid var(--line)',
                          borderRadius: 'var(--radius)',
                          padding: '10px 12px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 12,
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span
                              className="ref-link"
                              onClick={() => onOpenDoc(m.document_code)}
                            >
                              {m.document_code}
                            </span>
                            <span className="badge badge-info">Md. {m.clause_no}</span>
                            <span className="badge badge-ok">
                              Skor: %{(m.similarity_score * 100).toFixed(0)}
                            </span>
                            {m.heading && (
                              <span style={{ fontWeight: 600, fontSize: '13px' }}>{m.heading}</span>
                            )}
                          </div>
                          {m.quote && (
                            <div className="quote-box" style={{ margin: '6px 0 0', fontSize: '12.5px' }}>
                              "{m.quote}"
                            </div>
                          )}
                        </div>

                        <button
                          type="button"
                          className="primary"
                          onClick={() => matchingStepSeq && handleLinkClause(matchingStepSeq, m.document_code, m.clause_no)}
                          style={{ padding: '6px 12px', fontSize: '12.5px' }}
                        >
                          <Link2 size={13} />
                          <span>Bu Maddeye Bağla</span>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* New Decision Modal */}
      {showDecisionModal && (
        <div className="modal-backdrop" onClick={() => setShowDecisionModal(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Plus size={18} color="var(--accent)" />
                <h3 className="modal-title">Yeni Karar / Yetki Tanımı</h3>
              </div>
              <button className="icon-btn" onClick={() => setShowDecisionModal(false)}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleSaveDecision} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, marginBottom: 4 }}>
                  Karar Konusu / Karar Adı
                </label>
                <input
                  type="text"
                  placeholder="Örn: 100.000 TL üzeri satınalma onayı"
                  value={decisionTopic}
                  onChange={(e) => setDecisionTopic(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, marginBottom: 4 }}>
                  Karar Sahibi (Accountable - Onaylayan Rol)
                </label>
                <input
                  type="text"
                  placeholder="Örn: Genel Müdür"
                  value={decisionMaker}
                  onChange={(e) => setDecisionMaker(e.target.value)}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, marginBottom: 4 }}>
                  Yürüten / Sorumlu (Responsible)
                </label>
                <input
                  type="text"
                  placeholder="Örn: Satınalma Sorumlusu"
                  value={decisionResponsible}
                  onChange={(e) => setDecisionResponsible(e.target.value)}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, marginBottom: 4 }}>
                  Danışılan Roller (Consulted - virgülle ayırın)
                </label>
                <input
                  type="text"
                  placeholder="Örn: Mali İşler Müdürü, Kalite Müdürü"
                  value={decisionConsulted}
                  onChange={(e) => setDecisionConsulted(e.target.value)}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12.5px', fontWeight: 600, marginBottom: 4 }}>
                  Bilgilendirilen Roller (Informed - virgülle ayırın)
                </label>
                <input
                  type="text"
                  placeholder="Örn: İlgili Departman Müdürü"
                  value={decisionInformed}
                  onChange={(e) => setDecisionInformed(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setShowDecisionModal(false)}
                  style={{ flex: 1 }}
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  className="primary"
                  disabled={savingDecision}
                  style={{ flex: 1 }}
                >
                  {savingDecision ? 'Kaydediliyor...' : 'Kaydet'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
