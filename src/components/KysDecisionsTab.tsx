import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { kysApi, MatrixRowResult, MatrixRowStatus, MatrixDocCheck } from '../services/apiClient';
import { DecisionItem, DocumentSummary, FindingItem, RuleItem } from '../types/kys';
import {
  Scale,
  Plus,
  RefreshCw,
  Search,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  Check,
  X,
  Info,
  Trash2,
  Upload,
  Download,
  FileSpreadsheet,
} from 'lucide-react';

// Matris kontrolü: satırlar sunucuya parça parça gönderilir (eski arayüzdeki DEC_CHUNK ile aynı).
const MATRIX_CHUNK = 12;

const STATUS_LABEL: Record<MatrixRowStatus, string> = {
  KAYNAKLI: 'Kaynaklı',
  CELISKI: 'Prosedüre aykırı',
  KISMI: 'Kısmi',
  KAYNAK_YOK: 'Kaynak yok',
};
const STATUS_HINT: Record<MatrixRowStatus, string> = {
  KAYNAKLI: 'Dayanak bulundu; rol, limit ve süre dokümanla uyumlu.',
  CELISKI: 'Dokümanda farklı karar verici, limit veya süre yazıyor.',
  KISMI: 'Karar dokümanda geçiyor ama rol veya limit doğrulanamadı.',
  KAYNAK_YOK: 'Hiçbir KYS dokümanında dayanak bulunamadı.',
};
const DOC_CHECK_LABEL: Record<MatrixDocCheck, string> = {
  DOGRULANDI: 'Matristeki doküman doğrulandı',
  DESTEKLEMIYOR: 'Matristeki doküman desteklemiyor',
  SISTEMDE_YOK: 'Matristeki doküman sistemde yok',
};

const StatusTag: React.FC<{ status: MatrixRowStatus }> = ({ status }) => {
  if (status === 'KAYNAKLI') {
    return (
      <span className="kys-clean-label" title={STATUS_HINT[status]}>
        <CheckCircle2 size={13} className="text-ok shrink-0" />
        <span>{STATUS_LABEL[status]}</span>
      </span>
    );
  }
  return (
    <span className={`kys-finding-tag ${status === 'CELISKI' ? 'danger' : 'warn'}`} title={STATUS_HINT[status]}>
      {status === 'CELISKI' ? <ShieldAlert size={12} className="shrink-0" /> : <AlertTriangle size={12} className="shrink-0" />}
      <span>{STATUS_LABEL[status]}</span>
    </span>
  );
};

const roleText = (v: unknown): string => (Array.isArray(v) ? v.join(', ') : typeof v === 'string' ? v : '');

/** Karar matrisi (xlsx/csv) yükleme → her satır için kaynaklı kontrol → sonuç tablosu ve Excel. Hiçbir şey kaydedilmez. */
const MatrixCheckPanel: React.FC<{ onOpenDoc: (code: string) => void; onClose: () => void }> = ({ onOpenDoc, onClose }) => {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<MatrixRowResult[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [running, setRunning] = useState<boolean>(false);
  const [downloading, setDownloading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [missingDocs, setMissingDocs] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState<MatrixRowStatus | 'HEPSI'>('HEPSI');
  const [sheetFilter, setSheetFilter] = useState<string>('HEPSI');
  const [expanded, setExpanded] = useState<number | null>(null);
  const cancelRef = useRef<boolean>(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const run = async (f: File, resume: boolean) => {
    cancelRef.current = false;
    setRunning(true);
    setError(null);
    let done: MatrixRowResult[] = resume ? rows : [];
    if (!resume) {
      setRows([]);
      setTotal(0);
      setWarnings([]);
      setMissingDocs([]);
      setExpanded(null);
    }
    try {
      let tot = resume ? total : Infinity;
      while (done.length < tot && !cancelRef.current) {
        const res = await kysApi.checkDecisionMatrix(f, done.length, MATRIX_CHUNK);
        tot = res.aralik.toplam;
        setTotal(tot);
        if (done.length === 0) setWarnings(res.matris.uyarilar || []);
        if (res.satirlar.length === 0) break;
        done = [...done, ...res.satirlar];
        setRows(done);
        setMissingDocs((prev) => Array.from(new Set([...prev, ...res.ozet.sistemde_yok_dokumanlar])).sort());
      }
    } catch (err: unknown) {
      setError(
        (err instanceof Error ? err.message : 'Kontrol başarısız') +
          (done.length ? ` · ${done.length} satır tamamlandı; "Devam et" ile kalanlar işlenir.` : '')
      );
    } finally {
      setRunning(false);
    }
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    setFile(f);
    run(f, false);
  };

  const download = async () => {
    if (!file || rows.length === 0) return;
    setDownloading(true);
    try {
      const blob = await kysApi.downloadDecisionMatrixXlsx(file, rows);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.name.replace(/\.[^.]+$/, '') + '_kontrol.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Excel oluşturulamadı');
    } finally {
      setDownloading(false);
    }
  };

  const counts = useMemo(() => {
    const c: Record<MatrixRowStatus, number> = { KAYNAKLI: 0, CELISKI: 0, KISMI: 0, KAYNAK_YOK: 0 };
    rows.forEach((r) => (c[r.durum] += 1));
    return c;
  }, [rows]);
  const sheets = useMemo(() => Array.from(new Set(rows.map((r) => r.sayfa || '-'))), [rows]);
  const unverified = useMemo(() => rows.filter((r) => r.dogrulanmamis).length, [rows]);
  const shown = useMemo(
    () =>
      rows.filter(
        (r) => (statusFilter === 'HEPSI' || r.durum === statusFilter) && (sheetFilter === 'HEPSI' || (r.sayfa || '-') === sheetFilter)
      ),
    [rows, statusFilter, sheetFilter]
  );
  const pct = total ? Math.round((rows.length / total) * 100) : 0;
  // İlk parça bile gelmeden hata olduysa toplam bilinmez; yine de yeniden denenebilir.
  const incomplete = !running && file !== null && (total > 0 ? rows.length < total : error !== null);

  return (
    <div style={{ margin: '12px 16px', border: '1px solid var(--line)', borderRadius: 'var(--radius)', background: 'var(--panel)' }}>
      <div className="kys-grid-toolbar">
        <div className="kys-grid-title-group">
          <FileSpreadsheet size={16} className="text-accent" />
          <h2 className="kys-grid-title">Karar Matrisi Kontrolü</h2>
          {file && <span className="kys-grid-count font-mono">{file.name}</span>}
        </div>
        <div className="kys-grid-filters">
          <input ref={inputRef} type="file" accept=".xlsx,.xlsm,.csv" style={{ display: 'none' }} onChange={onPick} />
          <button type="button" className="icon-btn kys-run-audit-btn" onClick={() => inputRef.current?.click()} disabled={running}>
            <Upload size={14} />
            <span>{file ? 'Başka Dosya' : 'Excel Seç'}</span>
          </button>
          {running && (
            <button type="button" className="icon-btn" onClick={() => (cancelRef.current = true)}>
              <X size={14} />
              <span>Durdur</span>
            </button>
          )}
          {incomplete && (
            <button type="button" className="icon-btn" onClick={() => file && run(file, total > 0)}>
              <RefreshCw size={14} />
              <span>{rows.length ? 'Devam et' : 'Tekrar dene'}</span>
            </button>
          )}
          <button type="button" className="icon-btn" onClick={download} disabled={running || downloading || rows.length === 0}>
            <Download size={14} />
            <span>{downloading ? 'Hazırlanıyor...' : 'Excel İndir'}</span>
          </button>
          <button type="button" className="icon-btn" onClick={onClose} disabled={running} title="Kapat">
            <X size={14} />
          </button>
        </div>
      </div>

      {!file && (
        <div className="kys-info-box" style={{ margin: '12px 16px' }}>
          <Info size={16} className="text-accent shrink-0" />
          <p>
            Karar matrisinizi veya yetki limit tablonuzu (.xlsx / .csv; düz tablo ya da RACI) seçin. Her karar için
            yürürlükteki KYS dokümanlarında dayanak aranır; bulunan alıntı kaynak metne karşı doğrulanır. Matristeki
            karar verici, limit ve süre dokümanla karşılaştırılır; "İlgili Doküman" kolonu da ayrıca denetlenir.
            Dosya sunucuda saklanmaz, sonuçlar kaydedilmez.
          </p>
        </div>
      )}

      {file && (
        <div style={{ padding: '8px 16px' }}>
          <div style={{ height: 6, background: 'var(--line)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)', transition: 'width .3s' }} />
          </div>
          <div className="text-xs text-muted" style={{ marginTop: 4 }}>
            {total ? `${rows.length} / ${total} satır kontrol edildi` : running ? 'Dosya okunuyor...' : 'Kontrol tamamlanamadı'}
            {running && ' · çalışıyor (satır başına birkaç saniye sürebilir)'}
          </div>
        </div>
      )}

      {error && (
        <div className="kys-alert-banner danger" style={{ margin: '0 16px 12px' }} title={error}>
          <AlertTriangle size={16} />
          {/* Model zinciri hataları sağlayıcının ham JSON'unu taşır; tamamı title'da */}
          <span>{error.length > 280 ? `${error.slice(0, 280)}…` : error}</span>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="text-xs text-muted" style={{ margin: '0 16px 8px' }}>
          {warnings.map((w, i) => (
            <div key={i}>! {w}</div>
          ))}
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div className="kys-grid-filters" style={{ padding: '0 16px 8px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className={`icon-btn ${statusFilter === 'HEPSI' ? 'kys-run-audit-btn' : ''}`}
              onClick={() => setStatusFilter('HEPSI')}
            >
              Tümü ({rows.length})
            </button>
            {(Object.keys(STATUS_LABEL) as MatrixRowStatus[]).map((s) => (
              <button
                key={s}
                type="button"
                className={`icon-btn ${statusFilter === s ? 'kys-run-audit-btn' : ''}`}
                onClick={() => setStatusFilter(s)}
                title={STATUS_HINT[s]}
              >
                {STATUS_LABEL[s]} ({counts[s]})
              </button>
            ))}
            {sheets.length > 1 && (
              <select
                value={sheetFilter}
                onChange={(e) => setSheetFilter(e.target.value)}
                style={{ width: 'auto', padding: '4px 8px', fontSize: '12px' }}
              >
                <option value="HEPSI">Tüm sayfalar</option>
                {sheets.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
            {unverified > 0 && (
              <span className="text-xs text-muted">· {unverified} satır doğrulanmamış (onaysız) kurala dayanıyor</span>
            )}
          </div>
          {missingDocs.length > 0 && (
            <div className="text-xs text-muted" style={{ margin: '0 16px 8px' }}>
              Sistemde olmayan dokümanlar: <span className="font-mono">{missingDocs.join(', ')}</span>
            </div>
          )}

          <div className="kys-table-container">
            <table className="kys-table" aria-label="Karar Matrisi Kontrol Sonuçları">
              <thead>
                <tr>
                  <th scope="col" className="kys-th" style={{ width: '140px' }}>SAYFA / SATIR</th>
                  <th scope="col" className="kys-th">KARAR</th>
                  <th scope="col" className="kys-th" style={{ width: '170px' }}>KARAR VERİCİ (MATRİS)</th>
                  <th scope="col" className="kys-th" style={{ width: '200px' }}>DAYANAK</th>
                  <th scope="col" className="kys-th" style={{ width: '170px' }}>DURUM</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const key = r.no;
                  const open = expanded === key;
                  const deciders = roleText(r.girdi.karar_verici) || roleText(r.girdi.onaylayan) || roleText(r.girdi.yetkili);
                  return (
                    <React.Fragment key={key}>
                      <tr
                        className={`kys-table-row ${r.durum === 'CELISKI' ? 'has-findings' : ''}`}
                        onClick={() => setExpanded(open ? null : key)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="kys-td text-xs text-muted">
                          {r.sayfa || '-'} · {r.satir}
                        </td>
                        <td className="kys-td">
                          <span className="kys-doc-name">{r.karar}</span>
                          {typeof r.girdi.ilgili_dokuman === 'string' && r.girdi.ilgili_dokuman && (
                            <span className="kys-doc-summary-hint">Matristeki doküman: {r.girdi.ilgili_dokuman}</span>
                          )}
                        </td>
                        <td className="kys-td text-xs">{deciders || '—'}</td>
                        <td className="kys-td font-mono text-xs">
                          {r.kaynaklar.length === 0
                            ? <span className="text-muted">—</span>
                            : r.kaynaklar.map((s, i) => (
                                <div key={i}>
                                  {s.doc_code ? (
                                    <button
                                      type="button"
                                      className="kys-code-link"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        onOpenDoc(s.doc_code as string);
                                      }}
                                    >
                                      {s.doc_code}
                                      {s.revision ? ` Rev.${s.revision}` : ''}
                                      {s.clause_no ? ` M.${s.clause_no}` : ''}
                                    </button>
                                  ) : (
                                    <span className="text-muted">kodsuz doküman</span>
                                  )}
                                </div>
                              ))}
                        </td>
                        <td className="kys-td">
                          <StatusTag status={r.durum} />
                          {r.dogrulanmamis && (
                            <div className="text-xs text-muted" style={{ fontSize: '11px', marginTop: 2 }}>
                              [Doğrulanmamış kaynak]
                            </div>
                          )}
                          {r.dokuman_kontrolu && (
                            <div className="text-xs text-muted" style={{ fontSize: '11px', marginTop: 2 }}>
                              {DOC_CHECK_LABEL[r.dokuman_kontrolu]}
                            </div>
                          )}
                        </td>
                      </tr>
                      {open && (
                        <tr>
                          <td colSpan={5} className="kys-td" style={{ background: 'var(--panel-hover)' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontSize: '12px' }}>
                              <div>{r.aciklama}</div>
                              {r.celiskiler.map((c, i) => (
                                <div key={i} style={{ color: 'var(--danger)' }}>
                                  <strong>{c.alan}:</strong> matriste "{c.matris}", dokümanda "{c.dokuman}" ({c.kaynak})
                                </div>
                              ))}
                              {r.kaynaklar.map((s, i) => (
                                <blockquote
                                  key={i}
                                  style={{ margin: 0, padding: '6px 10px', borderLeft: '3px solid var(--accent)', background: 'var(--panel)' }}
                                >
                                  <div className="font-mono text-xs text-muted">
                                    {s.doc_code || 'kodsuz'}
                                    {s.revision ? ` Rev.${s.revision}` : ''}
                                    {s.clause_no ? ` · Madde ${s.clause_no}` : ''}
                                    {s.heading ? ` · ${s.heading}` : ''}
                                    {s.dogrulanmamis ? ' · [Doğrulanmamış kaynak]' : ''}
                                  </div>
                                  <div>"{s.quote}"</div>
                                </blockquote>
                              ))}
                              {r.uyarilar.length > 0 && (
                                <div className="text-xs text-muted">
                                  {r.uyarilar.map((w, i) => (
                                    <div key={i}>! {w}</div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};

export interface KysDecisionsTabProps {
  documents: DocumentSummary[];
  findings: FindingItem[];
  onOpenDoc: (code: string) => void;
  onRefreshData: () => void;
}

export interface DecisionVerificationResult {
  decisionId: number;
  status: 'VERIFIED' | 'MISSING_DOC' | 'MISSING_CLAUSE' | 'CONFLICT';
  message: string;
  matchedDoc?: DocumentSummary;
  matchedClauseText?: string;
  clashingRule?: RuleItem;
}

export const KysDecisionsTab: React.FC<KysDecisionsTabProps> = ({
  documents,
  findings,
  onOpenDoc,
  onRefreshData,
}) => {
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterProcess, setFilterProcess] = useState<string>('HEPSI');

  // New Decision Modal / Form State
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [savingDecision, setSavingDecision] = useState<boolean>(false);
  const [formTopic, setFormTopic] = useState<string>('');
  const [formProcessCode, setFormProcessCode] = useState<string>('PR-01');
  const [formDecisionMaker, setFormDecisionMaker] = useState<string>('');
  const [formResponsible, setFormResponsible] = useState<string>('');
  const [formLimitAmount, setFormLimitAmount] = useState<string>('');
  const [formSourceDoc, setFormSourceDoc] = useState<string>('');
  const [formSourceClause, setFormSourceClause] = useState<string>('');
  const [formRuleSummary, setFormRuleSummary] = useState<string>('');

  const [showMatrix, setShowMatrix] = useState<boolean>(false);

  // Verification Results cache
  const [verifications, setVerifications] = useState<Record<number, DecisionVerificationResult>>({});
  const [verifying, setVerifying] = useState<boolean>(false);

  // Fetch Decisions
  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kysApi.getDecisions();
      setDecisions(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Karar envanteri alınamadı');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDecisions();
  }, [fetchDecisions]);

  // Run Document Verification across all Decisions
  const verifyDecisionsAgainstDocs = useCallback(async (decisionList: DecisionItem[]) => {
    setVerifying(true);
    const results: Record<number, DecisionVerificationResult> = {};

    for (const dec of decisionList) {
      const docCode = dec.source_document?.trim().toUpperCase();
      const clause = dec.source_clause?.trim();

      // Case 1: No source document provided
      if (!docCode) {
        results[dec.id] = {
          decisionId: dec.id,
          status: 'MISSING_DOC',
          message: 'Belirtilen dayanak doküman yok veya tanımsız.',
        };
        continue;
      }

      // Find doc in documents
      const matchedDoc = documents.find(
        (d) => d.code?.trim().toUpperCase() === docCode
      );

      // Case 2: Document does not exist in library
      if (!matchedDoc) {
        results[dec.id] = {
          decisionId: dec.id,
          status: 'MISSING_DOC',
          message: `Dayanak doküman '${docCode}' sistem kütüphanesinde bulunamadı veya yürürlükten kalkmış.`,
        };
        continue;
      }

      // Check document detail for clause and rules
      try {
        const docDetail = await kysApi.getDocument(matchedDoc.code);
        let foundClause = false;
        let clauseText = '';

        if (clause && docDetail.sections) {
          const sec = docDetail.sections.find(
            (s) =>
              (s.clause_no && s.clause_no.trim() === clause) ||
              (s.heading && s.heading.includes(clause)) ||
              (s.text && s.text.includes(clause))
          );
          if (sec) {
            foundClause = true;
            clauseText = sec.text;
          }
        }

        if (clause && !foundClause) {
          results[dec.id] = {
            decisionId: dec.id,
            status: 'MISSING_CLAUSE',
            message: `Dayanak doküman '${docCode}' içinde Madde ${clause} bulunamadı.`,
            matchedDoc,
          };
          continue;
        }

        // Check if there is an active finding / conflict for this document
        const hasConflict = findings.some(
          (f) =>
            f.document_code === docCode &&
            (f.finding_type === 'YETKI_ASIMI' || f.finding_type === 'CAKISMA') &&
            f.status === 'ACIK'
        );

        if (hasConflict) {
          results[dec.id] = {
            decisionId: dec.id,
            status: 'CONFLICT',
            message: `Dokümanda aktif yetki aşımı veya kural çakışması tespit edildi.`,
            matchedDoc,
            matchedClauseText: clauseText,
          };
        } else {
          results[dec.id] = {
            decisionId: dec.id,
            status: 'VERIFIED',
            message: `Dayanak başarıyla doğrulandı: ${docCode}${clause ? ` (Madde ${clause})` : ''}`,
            matchedDoc,
            matchedClauseText: clauseText,
          };
        }
      } catch {
        results[dec.id] = {
          decisionId: dec.id,
          status: 'MISSING_DOC',
          message: `Doküman '${docCode}' ayrıntılarına erişilemedi.`,
          matchedDoc,
        };
      }
    }

    setVerifications(results);
    setVerifying(false);
  }, [documents, findings]);

  useEffect(() => {
    if (decisions.length > 0 && documents.length > 0) {
      verifyDecisionsAgainstDocs(decisions);
    }
  }, [decisions, documents, verifyDecisionsAgainstDocs]);

  // Handle Save New Decision
  const handleSaveDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTopic.trim() || !formDecisionMaker.trim()) {
      alert('Lütfen karar konusu ve karar verici alanlarını doldurunuz.');
      return;
    }

    setSavingDecision(true);
    try {
      const summaryText = formLimitAmount
        ? `Yetki Limiti: ${formLimitAmount} · ${formRuleSummary}`
        : formRuleSummary;

      await kysApi.createOrUpdateDecision({
        topic: formTopic.trim(),
        process_code: formProcessCode.trim().toUpperCase(),
        decision_maker: formDecisionMaker.trim(),
        responsible: formResponsible.trim() || null,
        source_document: formSourceDoc.trim().toUpperCase() || null,
        source_clause: formSourceClause.trim() || null,
        rule_summary: summaryText.trim() || null,
      });

      // Reset form
      setFormTopic('');
      setFormDecisionMaker('');
      setFormResponsible('');
      setFormLimitAmount('');
      setFormSourceDoc('');
      setFormSourceClause('');
      setFormRuleSummary('');
      setShowAddModal(false);

      await fetchDecisions();
      onRefreshData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Karar kaydedilemedi');
    } finally {
      setSavingDecision(false);
    }
  };

  const handleDeleteDecision = async (id: number) => {
    if (!window.confirm('Bu karar kaydını silmek istediğinize emin misiniz?')) return;
    try {
      await kysApi.deleteDecision(id);
      setDecisions((prev) => prev.filter((d) => d.id !== id));
      onRefreshData();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Karar silinemedi');
    }
  };

  // Distinct process codes
  const processCodes = useMemo(() => {
    const set = new Set<string>();
    decisions.forEach((d) => {
      if (d.process_code) set.add(d.process_code);
    });
    return Array.from(set).sort();
  }, [decisions]);

  // Filtered decisions
  const filteredDecisions = useMemo(() => {
    return decisions.filter((d) => {
      if (filterProcess !== 'HEPSI' && d.process_code !== filterProcess) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const tMatch = d.topic?.toLowerCase().includes(q);
        const mMatch = d.decision_maker?.toLowerCase().includes(q);
        const rMatch = d.responsible?.toLowerCase().includes(q);
        const dMatch = d.source_document?.toLowerCase().includes(q);
        if (!tMatch && !mMatch && !rMatch && !dMatch) return false;
      }
      return true;
    });
  }, [decisions, filterProcess, searchQuery]);

  return (
    <div className="kys-grid-wrapper">
      {/* Top Toolbar */}
      <div className="kys-grid-toolbar">
        <div className="kys-grid-title-group">
          <Scale size={16} className="text-accent" />
          <h2 className="kys-grid-title">Karar Envanteri ve Yetki Limit Tablosu</h2>
          <span className="kys-grid-count font-mono">
            {filteredDecisions.length} kayıt
          </span>
          {verifying && (
            <span className="text-muted text-xs">· Dayanaklar denetleniyor...</span>
          )}
        </div>

        <div className="kys-grid-filters">
          {/* Process Filter */}
          <div className="kys-filter-group">
            <span className="kys-filter-label">Süreç:</span>
            <select
              value={filterProcess}
              onChange={(e) => setFilterProcess(e.target.value)}
              style={{ width: 'auto', padding: '4px 8px', fontSize: '12px' }}
            >
              <option value="HEPSI">Tüm Süreçler</option>
              {processCodes.map((pc) => (
                <option key={pc} value={pc}>
                  {pc}
                </option>
              ))}
            </select>
          </div>

          {/* Search Input */}
          <div style={{ position: 'relative', width: '220px' }}>
            <Search size={13} className="kys-search-icon" />
            <input
              type="text"
              className="kys-search-input"
              placeholder="Konu, yetkili veya dayanak ara..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '28px', fontSize: '12px' }}
            />
          </div>

          <button
            type="button"
            className="icon-btn"
            onClick={fetchDecisions}
            disabled={loading}
            title="Yenile"
          >
            <RefreshCw
              size={14}
              style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
            />
          </button>

          <button
            type="button"
            className="icon-btn kys-run-audit-btn"
            onClick={() => setShowMatrix(true)}
            disabled={showMatrix}
          >
            <Upload size={14} />
            <span>Matris Yükle ve Kontrol Et</span>
          </button>

          <button
            type="button"
            className="icon-btn kys-run-audit-btn"
            onClick={() => setShowAddModal(true)}
          >
            <Plus size={14} />
            <span>Yeni Karar / Yetki Ekle</span>
          </button>
        </div>
      </div>

      {showMatrix && <MatrixCheckPanel onOpenDoc={onOpenDoc} onClose={() => setShowMatrix(false)} />}

      {/* Info notice */}
      <div className="kys-info-box" style={{ margin: '12px 16px' }}>
        <Info size={16} className="text-accent shrink-0" />
        <p>
          <strong>Otomatik Dayanak ve Yetki Denetimi:</strong> Eklenen her kararın dayanak doküman kodu
          ve madde numarası, yürürlükteki KYS doküman kütüphanesiyle otomatik karşılaştırılır. Dayanağı
          olmayan veya kural çakışması olan kararlar Denetim Radarı tarafından uyarılır.
        </p>
      </div>

      {error && (
        <div className="kys-alert-banner danger" style={{ margin: '0 16px 12px' }}>
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* High-Density Decisions Table */}
      <div className="kys-table-container">
        <table className="kys-table" aria-label="Karar Envanteri Tablosu">
          <thead>
            <tr>
              <th scope="col" className="kys-th" style={{ width: '100px' }}>SÜREÇ</th>
              <th scope="col" className="kys-th">KARAR KONUSU & KURAL</th>
              <th scope="col" className="kys-th" style={{ width: '160px' }}>KARAR VERİCİ</th>
              <th scope="col" className="kys-th" style={{ width: '140px' }}>SORUMLU</th>
              <th scope="col" className="kys-th" style={{ width: '160px' }}>DAYANAK DOKÜMAN</th>
              <th scope="col" className="kys-th" style={{ width: '220px' }}>DENETİM & DAYANAK DURUMU</th>
              <th scope="col" className="kys-th" style={{ width: '60px', textAlign: 'right' }}>İŞLEM</th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="kys-skeleton-row">
                  <td colSpan={7}>
                    <div className="kys-skeleton-bar" />
                  </td>
                </tr>
              ))
            ) : filteredDecisions.length === 0 ? (
              <tr>
                <td colSpan={7} className="kys-empty-cell">
                  <div className="kys-empty-box">
                    <Scale size={28} className="text-muted" />
                    <p className="kys-empty-title">Kayıtlı karar veya yetki kuralı bulunamadı.</p>
                    <p className="kys-empty-sub">
                      Yukarıdaki "Yeni Karar / Yetki Ekle" butonu ile karar ekleyebilirsiniz.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              filteredDecisions.map((dec) => {
                const verif = verifications[dec.id];
                const isVerified = verif?.status === 'VERIFIED';
                const isConflict = verif?.status === 'CONFLICT';
                const isMissing = verif?.status === 'MISSING_DOC' || verif?.status === 'MISSING_CLAUSE';

                return (
                  <tr key={dec.id} className={`kys-table-row ${isConflict ? 'has-findings' : ''}`}>
                    {/* Process */}
                    <td className="kys-td font-mono font-bold text-accent">
                      {dec.process_code}
                    </td>

                    {/* Topic & Summary */}
                    <td className="kys-td">
                      <span className="kys-doc-name">{dec.topic}</span>
                      {dec.rule_summary && (
                        <span className="kys-doc-summary-hint">{dec.rule_summary}</span>
                      )}
                    </td>

                    {/* Decision Maker */}
                    <td className="kys-td font-medium text-xs">
                      {dec.decision_maker}
                    </td>

                    {/* Responsible */}
                    <td className="kys-td text-xs text-muted">
                      {dec.responsible || '—'}
                    </td>

                    {/* Source Document & Clause */}
                    <td className="kys-td font-mono text-xs">
                      {dec.source_document ? (
                        <button
                          type="button"
                          className="kys-code-link"
                          onClick={() => onOpenDoc(dec.source_document as string)}
                          title="Dokümanı İncele"
                        >
                          {dec.source_document}
                          {dec.source_clause ? ` M.${dec.source_clause}` : ''}
                        </button>
                      ) : (
                        <span className="text-muted">Tanımsız</span>
                      )}
                    </td>

                    {/* Verification Status */}
                    <td className="kys-td">
                      {isVerified ? (
                        <span className="kys-clean-label">
                          <CheckCircle2 size={13} className="text-ok shrink-0" />
                          <span>Doğrulandı</span>
                        </span>
                      ) : isConflict ? (
                        <span className="kys-finding-tag danger" title={verif?.message}>
                          <ShieldAlert size={12} className="shrink-0" />
                          <span>Yetki / Kural Çelişkisi</span>
                        </span>
                      ) : isMissing ? (
                        <span className="kys-finding-tag warn" title={verif?.message}>
                          <AlertTriangle size={12} className="shrink-0" />
                          <span>Dayanak Bulunamadı</span>
                        </span>
                      ) : (
                        <span className="text-muted text-xs">Kontrol ediliyor...</span>
                      )}
                      {verif?.message && (
                        <div
                          className="text-xs text-muted"
                          style={{ fontSize: '11px', marginTop: 2, lineHeight: 1.2 }}
                        >
                          {verif.message}
                        </div>
                      )}
                    </td>

                    {/* Action */}
                    <td className="kys-td text-right">
                      <button
                        type="button"
                        className="kys-row-action-btn"
                        onClick={() => handleDeleteDecision(dec.id)}
                        title="Kararı Sil"
                      >
                        <Trash2 size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Add Decision Modal */}
      {showAddModal && (
        <div
          className="kys-modal-backdrop"
          onClick={() => setShowAddModal(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="kys-modal-container"
            style={{ maxWidth: '600px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="kys-modal-header">
              <div className="kys-modal-title-group">
                <Scale size={18} className="text-accent" />
                <h3>Yeni Karar ve Yetki Limiti Ekle</h3>
              </div>
              <button
                type="button"
                className="icon-btn kys-modal-close"
                onClick={() => setShowAddModal(false)}
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleSaveDecision} className="kys-modal-body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                    Karar / Yetki Konusu *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Örn: 50.000 TL Üzeri Satın Alma Onayı"
                    value={formTopic}
                    onChange={(e) => setFormTopic(e.target.value)}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Süreç Kodu *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="Örn: PR-01"
                      value={formProcessCode}
                      onChange={(e) => setFormProcessCode(e.target.value)}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Yetki Limiti / Eşik Tutarı
                    </label>
                    <input
                      type="text"
                      placeholder="Örn: 100.000 TL veya Maks 3 Gün"
                      value={formLimitAmount}
                      onChange={(e) => setFormLimitAmount(e.target.value)}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Karar Verici (Rol / Makam) *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="Örn: Genel Müdür / Satın Alma Müdürü"
                      value={formDecisionMaker}
                      onChange={(e) => setFormDecisionMaker(e.target.value)}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Sorumlu Birim / Rol
                    </label>
                    <input
                      type="text"
                      placeholder="Örn: Satın Alma Uzmanı"
                      value={formResponsible}
                      onChange={(e) => setFormResponsible(e.target.value)}
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 10 }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Dayanak Doküman Kodu (Kütüphaneden)
                    </label>
                    <input
                      type="text"
                      placeholder="Örn: PR-01"
                      value={formSourceDoc}
                      onChange={(e) => setFormSourceDoc(e.target.value)}
                    />
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                      Dayanak Madde No
                    </label>
                    <input
                      type="text"
                      placeholder="Örn: 4.2"
                      value={formSourceClause}
                      onChange={(e) => setFormSourceClause(e.target.value)}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: 4 }}>
                    Kural / İş Akışı Özeti
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Örn: Teklif değerlendirme komisyonu onayı ve Genel Müdür nihai imzası gereklidir."
                    value={formRuleSummary}
                    onChange={(e) => setFormRuleSummary(e.target.value)}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 10 }}>
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => setShowAddModal(false)}
                    disabled={savingDecision}
                  >
                    Vazgeç
                  </button>
                  <button
                    type="submit"
                    className="icon-btn kys-run-audit-btn"
                    disabled={savingDecision}
                  >
                    <Check size={14} />
                    <span>{savingDecision ? 'Kaydediliyor...' : 'Kaydet ve Doğrula'}</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
