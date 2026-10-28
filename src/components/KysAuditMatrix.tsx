import React, { useState, useMemo } from 'react';
import { kysApi } from '../services/apiClient';
import { FindingItem, FindingStatus, SeverityType, ReferencesResponse } from '../types/kys';
import {
  ShieldAlert,
  AlertTriangle,
  Link2,
  RefreshCw,
  Play,
  CheckCircle2,
  Sparkles,
  ExternalLink,
  Check,
  X,
  FileText,
  Scale,
} from 'lucide-react';

export interface KysAuditMatrixProps {
  mode: 'CONFLICTS' | 'GAPS' | 'MISSING_REFS';
  findings: FindingItem[];
  missingRefs: ReferencesResponse | null;
  loading: boolean;
  onRefresh: () => void;
  onRunAudit: () => void;
  runningAudit: boolean;
  onOpenDoc: (code: string, tab?: 'content' | 'conflicts' | 'gaps') => void;
  onStatsChanged?: () => void;
}

export const KysAuditMatrix: React.FC<KysAuditMatrixProps> = ({
  mode,
  findings,
  missingRefs,
  loading,
  onRefresh,
  onRunAudit,
  runningAudit,
  onOpenDoc,
  onStatsChanged,
}) => {
  const [statusFilter, setStatusFilter] = useState<FindingStatus | 'HEPSI'>('ACIK');
  const [severityFilter, setSeverityFilter] = useState<SeverityType | 'HEPSI'>('HEPSI');
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  // Filter findings according to mode
  const displayedFindings = useMemo(() => {
    return findings.filter((f) => {
      // 1. Mode Filter
      if (mode === 'CONFLICTS') {
        if (f.finding_type !== 'CAKISMA' && f.finding_type !== 'YETKI_ASIMI' && f.finding_type !== 'BELIRSIZLIK') {
          return false;
        }
      } else if (mode === 'GAPS') {
        if (f.finding_type !== 'BOSLUK' && f.finding_type !== 'EKSIK_ONAY' && f.finding_type !== 'GUNCELLIK' && f.finding_type !== 'UYGUNSUZLUK') {
          return false;
        }
      }

      // 2. Status Filter
      if (statusFilter !== 'HEPSI' && f.status !== statusFilter) {
        return false;
      }

      // 3. Severity Filter
      if (severityFilter !== 'HEPSI' && f.severity !== severityFilter) {
        return false;
      }

      return true;
    });
  }, [findings, mode, statusFilter, severityFilter]);

  const handleUpdateStatus = async (id: number, newStatus: FindingStatus) => {
    setUpdatingId(id);
    try {
      await kysApi.updateFindingStatus(id, newStatus);
      if (onStatsChanged) onStatsChanged();
      onRefresh();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Durum güncellenemedi');
    } finally {
      setUpdatingId(null);
    }
  };

  const getActionableProposal = (f: FindingItem): string => {
    if (f.resolution_notes) return f.resolution_notes;
    switch (f.finding_type) {
      case 'CAKISMA':
        return `İlgili iki doküman arasındaki süre/eşik değeri ISO 9001 standardı gözetilerek üst dokümandaki kurala göre eşitlenmeli ve revize edilmelidir.`;
      case 'YETKI_ASIMI':
        return `Onay makamı şirketin imza sirküleri ve yetki matrisine göre netleştirilmeli, yetki aşımı riski giderilmelidir.`;
      case 'BOSLUK':
        return `Süreç akışında eksik kalan sorumlu rol ve kayıt formu belirlenerek ilgili maddeye açıkça eklenmelidir.`;
      case 'EKSIK_ONAY':
        return `Kontrolsüz işlem yapılmasını önlemek için süreç adımına 'Birim Amiri Onayı' aşaması eklenmelidir.`;
      case 'GUNCELLIK':
        return `İptal edilen forma yapılan atıf yürürlükteki güncel doküman kodu ile değiştirilmelidir.`;
      case 'BELIRSIZLIK':
        return `'İvedilikle' veya 'gerekli görüldüğünde' gibi yoruma açık ifadeler sayısal bir zaman sınırı ile netleştirilmelidir.`;
      default:
        return `KYS Denetim prensiplerine uygun revizyon yapılması önerilir.`;
    }
  };

  const getHeaderTitle = () => {
    switch (mode) {
      case 'CONFLICTS':
        return 'Dokümanlar Arası Kural Çelişkileri Radarı (Çakışma Analizi)';
      case 'GAPS':
        return 'Açık Kalan Noktalar ve KYS İyileştirme Önerileri (Boşluk Analizi)';
      case 'MISSING_REFS':
        return 'Eksik / İptal Doküman Atıfları Matrisi';
    }
  };

  const getHeaderDesc = () => {
    switch (mode) {
      case 'CONFLICTS':
        return 'Dokümanların birbirleriyle uyuşmayan süre, eşik ve yetki kuralları "Kanıtsız bulgu yok" ilkesiyle birebir alıntı ve madde referansıyla tespit edilmiştir.';
      case 'GAPS':
        return 'Tanımlanmamış onaycılar, süreç boşlukları, rol eksiklikleri ve belirsiz bırakılmış KYS gereksinimleri için somut iyileştirme önerileri listelenir.';
      case 'MISSING_REFS':
        return 'Yürürlükteki dokümanların atıfta bulunduğu ancak sistemde kaydı bulunmayan veya iptal edilmiş dış/iç referanslar.';
    }
  };

  return (
    <div className="kys-matrix-wrapper">
      {/* Matrix Header */}
      <div className="kys-matrix-header-card">
        <div className="kys-matrix-title-row">
          <div className="kys-matrix-title-group">
            {mode === 'CONFLICTS' ? (
              <ShieldAlert size={20} className="text-danger" />
            ) : mode === 'GAPS' ? (
              <AlertTriangle size={20} className="text-warn" />
            ) : (
              <Link2 size={20} className="text-accent" />
            )}
            <div>
              <h2 className="kys-matrix-title">{getHeaderTitle()}</h2>
              <p className="kys-matrix-desc">{getHeaderDesc()}</p>
            </div>
          </div>

          <div className="kys-matrix-actions">
            <button
              type="button"
              className="icon-btn kys-run-audit-btn"
              onClick={onRunAudit}
              disabled={runningAudit}
              title="Yeni Denetim ve Çakışma Analizi Çalıştır"
            >
              <Play
                size={13}
                style={{ animation: runningAudit ? 'spin 1s linear infinite' : 'none' }}
              />
              <span>{runningAudit ? 'Analiz Ediliyor...' : 'Yeniden Analiz Et'}</span>
            </button>

            <button
              type="button"
              className="icon-btn"
              onClick={onRefresh}
              disabled={loading}
              title="Yenile"
            >
              <RefreshCw
                size={14}
                style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
              />
            </button>
          </div>
        </div>

        {/* Filter Toolbar for Findings */}
        {mode !== 'MISSING_REFS' && (
          <div className="kys-matrix-filters-bar">
            {/* Status Segmented */}
            <div className="kys-filter-group">
              <span className="kys-filter-label">Durum:</span>
              <div className="kys-status-segmented">
                <button
                  type="button"
                  className={`kys-seg-btn ${statusFilter === 'ACIK' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('ACIK')}
                >
                  Açık Bulgular
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${statusFilter === 'KABUL' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('KABUL')}
                >
                  Kabul Edilen
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${statusFilter === 'COZULDU' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('COZULDU')}
                >
                  Çözüldü
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${statusFilter === 'HEPSI' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('HEPSI')}
                >
                  Tümü
                </button>
              </div>
            </div>

            {/* Severity Segmented */}
            <div className="kys-filter-group">
              <span className="kys-filter-label">Önem Derecesi:</span>
              <div className="kys-status-segmented">
                <button
                  type="button"
                  className={`kys-seg-btn ${severityFilter === 'HEPSI' ? 'active' : ''}`}
                  onClick={() => setSeverityFilter('HEPSI')}
                >
                  Tümü
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${severityFilter === 'KRITIK' ? 'active danger' : ''}`}
                  onClick={() => setSeverityFilter('KRITIK')}
                >
                  Kritik
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${severityFilter === 'ORTA' ? 'active warn' : ''}`}
                  onClick={() => setSeverityFilter('ORTA')}
                >
                  Orta
                </button>
                <button
                  type="button"
                  className={`kys-seg-btn ${severityFilter === 'DUSUK' ? 'active' : ''}`}
                  onClick={() => setSeverityFilter('DUSUK')}
                >
                  Düşük
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Content Area */}
      {mode === 'MISSING_REFS' ? (
        <div className="kys-matrix-content">
          {!missingRefs || missingRefs.missing_documents.length === 0 ? (
            <div className="kys-clean-state-card">
              <CheckCircle2 size={32} className="text-ok" />
              <h4>Sistemde Eksik veya Çözümlenemeyen Doküman Atıfı Yok</h4>
              <p>Tüm doküman atıfları sistemde tanımlı ve yürürlükteki belgelerle eşleşmektedir.</p>
            </div>
          ) : (
            <div className="kys-missing-refs-grid">
              {missingRefs.missing_documents.map((m, idx) => (
                <div key={idx} className="kys-missing-ref-card">
                  <div className="kys-missing-ref-header">
                    <span className="kys-missing-ref-code font-mono">{m.code}</span>
                    <span className="kys-missing-ref-badge">Tanımsız / Eksik Doküman</span>
                  </div>
                  <p className="kys-missing-ref-desc">
                    Bu doküman kodu diğer belgelere referans verilmiş ancak arşivde veya sistemde kaydı
                    bulunamamıştır.
                  </p>
                  <div className="kys-missing-ref-from">
                    <span className="text-muted text-xs">Atıf Yapan Dokümanlar:</span>
                    <div className="kys-ref-from-tags">
                      {m.referenced_from.map((refCode) => (
                        <button
                          key={refCode}
                          type="button"
                          className="kys-doc-jump-btn font-mono"
                          onClick={() => onOpenDoc(refCode, 'content')}
                        >
                          <FileText size={11} />
                          <span>{refCode}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="kys-matrix-content">
          {displayedFindings.length === 0 ? (
            <div className="kys-clean-state-card">
              <CheckCircle2 size={32} className="text-ok" />
              <h4>
                {mode === 'CONFLICTS'
                  ? 'Kriterlere Uygun Kural Çakışması Bulunmuyor'
                  : 'Kriterlere Uygun Açık Nokta Bulunmuyor'}
              </h4>
              <p>Filtre kriterlerini gevşetebilir veya "Yeniden Analiz Et" butonuna basabilirsiniz.</p>
            </div>
          ) : (
            <div className="kys-findings-matrix-list">
              {displayedFindings.map((finding) => (
                <article
                  key={finding.id}
                  className={`kys-matrix-finding-card severity-${finding.severity.toLowerCase()}`}
                >
                  {/* Card Header */}
                  <div className="kys-finding-card-header">
                    <div className="kys-finding-tags-row">
                      {finding.document_code && (
                        <button
                          type="button"
                          className="kys-card-doc-code font-mono"
                          onClick={() =>
                            onOpenDoc(
                              finding.document_code as string,
                              mode === 'CONFLICTS' ? 'conflicts' : 'gaps'
                            )
                          }
                          title="Bu dokümanın ayrıntılarını aç"
                        >
                          <FileText size={12} />
                          <span>{finding.document_code}</span>
                          <ExternalLink size={10} />
                        </button>
                      )}

                      <span className={`kys-severity-tag ${finding.severity.toLowerCase()}`}>
                        {finding.severity}
                      </span>

                      <span className="kys-finding-type-tag">
                        {finding.finding_type === 'CAKISMA'
                          ? 'Kural Çakışması'
                          : finding.finding_type === 'YETKI_ASIMI'
                          ? 'Yetki Uyuşmazlığı'
                          : finding.finding_type === 'BOSLUK'
                          ? 'Süreç / Rol Boşluğu'
                          : finding.finding_type === 'EKSIK_ONAY'
                          ? 'Eksik Onaycı'
                          : finding.finding_type === 'GUNCELLIK'
                          ? 'İptal Forma Atıf'
                          : 'Uyumsuzluk'}
                      </span>

                      <span className={`kys-status-label mini ${finding.status.toLowerCase()}`}>
                        {finding.status === 'ACIK'
                          ? 'Açık'
                          : finding.status === 'KABUL'
                          ? 'Kabul Edildi'
                          : finding.status === 'COZULDU'
                          ? 'Çözüldü'
                          : 'Yanlış Pozitif'}
                      </span>
                    </div>

                    <h3 className="kys-finding-title">{finding.title}</h3>
                  </div>

                  {/* Description */}
                  <p className="kys-finding-desc">{finding.description}</p>

                  {/* Evidence Comparison */}
                  {mode === 'CONFLICTS' ? (
                    <div className="kys-evidence-comparison">
                      <div className="kys-evidence-side current-doc">
                        <div className="kys-evidence-side-header">
                          <span className="kys-evidence-doc-label font-mono">
                            Kaynak: {finding.document_code || 'Doküman'}
                          </span>
                          <span className="kys-evidence-tag">Birinci Kural</span>
                        </div>
                        <div className="kys-evidence-quote-box">
                          <p className="kys-evidence-quote">
                            "{finding.evidence_quote || 'Dokümandaki madde hükmü'}"
                          </p>
                        </div>
                      </div>

                      <div className="kys-evidence-vs">
                        <Scale size={16} />
                        <span>VS</span>
                      </div>

                      <div className="kys-evidence-side clash-doc">
                        <div className="kys-evidence-side-header">
                          <span className="kys-evidence-doc-label font-mono">
                            Çelişen Karşı Kural / Doküman
                          </span>
                          <span className="kys-evidence-tag clash">Uyuşmazlık</span>
                        </div>
                        <div className="kys-evidence-quote-box clash">
                          <p className="kys-evidence-quote">{finding.description}</p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    finding.evidence_quote && (
                      <div className="kys-gap-evidence-box">
                        <span className="kys-gap-evidence-label">Tespit Edilen Madde Metni:</span>
                        <p className="kys-gap-evidence-quote">"{finding.evidence_quote}"</p>
                      </div>
                    )
                  )}

                  {/* KYS Actionable Proposal (Öneri) */}
                  <div className="kys-actionable-proposal-box">
                    <div className="kys-proposal-header">
                      <Sparkles size={14} className="text-accent" />
                      <span className="kys-proposal-title">
                        {mode === 'CONFLICTS'
                          ? 'KYS Çözüm & Hizalama Önerisi:'
                          : 'Önerilen KYS Revizyon Formülasyonu:'}
                      </span>
                    </div>
                    <p className="kys-proposal-text">{getActionableProposal(finding)}</p>
                  </div>

                  {/* Action Bar */}
                  <div className="kys-finding-action-row">
                    <span className="text-muted text-xs">Durum Değiştir:</span>
                    <button
                      type="button"
                      className="kys-action-chip ok"
                      disabled={updatingId === finding.id}
                      onClick={() => handleUpdateStatus(finding.id, 'COZULDU')}
                    >
                      <Check size={12} />
                      <span>Çözüldü</span>
                    </button>

                    <button
                      type="button"
                      className="kys-action-chip accept"
                      disabled={updatingId === finding.id}
                      onClick={() => handleUpdateStatus(finding.id, 'KABUL')}
                    >
                      <span>Kabul Edildi</span>
                    </button>

                    <button
                      type="button"
                      className="kys-action-chip dismiss"
                      disabled={updatingId === finding.id}
                      onClick={() => handleUpdateStatus(finding.id, 'YANLIS_POZITIF')}
                    >
                      <X size={12} />
                      <span>Yanlış Pozitif</span>
                    </button>

                    {finding.document_code && (
                      <button
                        type="button"
                        className="kys-action-chip jump ml-auto"
                        onClick={() =>
                          onOpenDoc(
                            finding.document_code as string,
                            mode === 'CONFLICTS' ? 'conflicts' : 'gaps'
                          )
                        }
                      >
                        <ExternalLink size={12} />
                        <span>Dokümanda İncele</span>
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
