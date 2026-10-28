import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import {
  DocumentDetail,
  FindingItem,
  FindingStatus,
  RuleItem,
} from '../types/kys';
import {
  ArrowLeft,
  FileText,
  ShieldAlert,
  AlertTriangle,
  Link2,
  CheckCircle2,
  AlertCircle,
  Check,
  X,
  Sparkles,
  Info,
  Scale,
  RefreshCw,
  Image as ImageIcon,
} from 'lucide-react';

export interface KysDocDetailProps {
  code: string;
  initialTab?: 'content' | 'conflicts' | 'gaps';
  onClose: () => void;
  onOpenDoc: (code: string) => void;
  onRefreshStats?: () => void;
}

export const KysDocDetail: React.FC<KysDocDetailProps> = ({
  code,
  initialTab = 'content',
  onClose,
  onOpenDoc,
  onRefreshStats,
}) => {
  const [activeTab, setActiveTab] = useState<'content' | 'conflicts' | 'gaps'>(initialTab);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [rules, setRules] = useState<RuleItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingFindingId, setUpdatingFindingId] = useState<number | null>(null);

  // PDF Preview
  const [previewPage, setPreviewPage] = useState<number | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState<boolean>(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [docData, allFindings, docRules] = await Promise.all([
        kysApi.getDocument(code),
        kysApi.getFindings({ limit: 200 }),
        kysApi.getRules({ doc_code: code }).catch(() => [] as RuleItem[]),
      ]);

      setDetail(docData);
      const relevantFindings = allFindings.filter(
        (f) =>
          f.document_code === code ||
          (f.description && f.description.includes(code)) ||
          (f.title && f.title.includes(code))
      );
      setFindings(relevantFindings);
      setRules(docRules);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Doküman verileri alınamadı');
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleUpdateFindingStatus = async (
    id: number,
    newStatus: FindingStatus,
    notes?: string
  ) => {
    setUpdatingFindingId(id);
    try {
      await kysApi.updateFindingStatus(id, newStatus, notes);
      setFindings((prev) =>
        prev.map((f) => (f.id === id ? { ...f, status: newStatus, resolution_notes: notes } : f))
      );
      if (onRefreshStats) onRefreshStats();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Durum güncellenemedi');
    } finally {
      setUpdatingFindingId(null);
    }
  };

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

  const conflictFindings = findings.filter(
    (f) => f.finding_type === 'CAKISMA' || f.finding_type === 'YETKI_ASIMI' || f.finding_type === 'BELIRSIZLIK'
  );

  const gapFindings = findings.filter(
    (f) =>
      f.finding_type === 'BOSLUK' ||
      f.finding_type === 'EKSIK_ONAY' ||
      f.finding_type === 'GUNCELLIK' ||
      f.finding_type === 'UYGUNSUZLUK'
  );

  const generateActionableSuggestion = (finding: FindingItem): string => {
    if (finding.resolution_notes) {
      return finding.resolution_notes;
    }
    switch (finding.finding_type) {
      case 'CAKISMA':
        return `İki dokümandaki çelişen eşik veya yetki ifadesi standartlaştırılmalıdır. Üst hiyerarşik dokümandaki kural esas alınarak ilgili madde için revizyon teklifi hazırlanması önerilir.`;
      case 'YETKI_ASIMI':
        return `Madde içerisindeki karar ve onay yetkisi, Şirket İmza Sirküleri ve Yetki Matrisi ile uyumlu hale getirilmeli; onay mercisi açıkça belirtilmelidir.`;
      case 'BOSLUK':
        return `Bu maddede tanımlanan süreç adımı için somut bir sorumlu rol atanmalı ve adımın tamamlandığına dair kayıt/form referansı eklenmelidir.`;
      case 'EKSIK_ONAY':
        return `Süreç akışında eksik kalan onay adımı için 'Birim Yöneticisi' veya 'Kalite Güvence Müdürü' kontrol noktası eklenmelidir.`;
      case 'GUNCELLIK':
        return `İptal edilmiş forma veya dokümana yapılan atıf kaldırılmalı, güncel yürürlükteki form kodu referans gösterilmelidir.`;
      case 'BELIRSIZLIK':
        return `'Mümkün olan en kısa sürede' veya 'uygun görüldüğünde' gibi muğlak ifadeler yerine ölçülebilir sayısal süre (örn. '2 iş günü içinde') tanımlanmalıdır.`;
      default:
        return `KYS Denetim standartları uyarınca ilgili maddede revizyon ve netleştirme yapılması tavsiye edilir.`;
    }
  };

  return (
    <div className="kys-detail-view">
      {/* Detail Top Navigation */}
      <div className="kys-detail-toolbar">
        <button
          type="button"
          className="icon-btn kys-back-btn"
          onClick={onClose}
          title="Doküman Listesine Dön"
        >
          <ArrowLeft size={15} />
          <span>Doküman Listesine Dön</span>
        </button>

        <button
          type="button"
          className="icon-btn"
          onClick={fetchData}
          disabled={loading}
          title="Yenile"
        >
          <RefreshCw
            size={14}
            style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }}
          />
        </button>
      </div>

      {loading && (
        <div className="kys-loading-card">
          <p>
            Doküman verileri ve çelişki analizleri yükleniyor: <strong>{code}</strong>...
          </p>
        </div>
      )}

      {error && (
        <div className="kys-alert-banner danger">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {detail && (
        <>
          {/* Document Header Card */}
          <div className="kys-detail-header-card">
            <div className="kys-header-card-top">
              <div className="kys-header-title-area">
                <div className="kys-code-badge-row">
                  <span className="kys-doc-code-pill font-mono">{detail.code}</span>
                  <span className="kys-meta-tag font-mono">Rev: {detail.revision || '00'}</span>
                  <span className="kys-meta-tag">{detail.doc_type}</span>
                  <span className={`kys-status-label ${detail.status?.toLowerCase()}`}>
                    {detail.status === 'YURURLUKTE'
                      ? 'Yürürlükte'
                      : detail.status === 'REVIZYONDA'
                      ? 'Revizyonda'
                      : detail.status === 'IPTAL'
                      ? 'İptal'
                      : detail.status}
                  </span>
                </div>
                <h1 className="kys-detail-main-title">{detail.title}</h1>
                {detail.summary && (
                  <p className="kys-detail-summary-text">{detail.summary}</p>
                )}
              </div>

              {/* Quick Status Highlights */}
              <div className="kys-header-highlights">
                <div className="kys-highlight-box">
                  <span className="kys-highlight-label">Sorumlu Birim</span>
                  <span className="kys-highlight-value">{detail.owner_unit || 'Tanımsız'}</span>
                </div>

                <div className="kys-highlight-box">
                  <span className="kys-highlight-label">Yürürlük Tarihi</span>
                  <span className="kys-highlight-value font-mono">
                    {detail.effective_date || detail.revision_date || '—'}
                  </span>
                </div>

                <div className="kys-highlight-box">
                  <span className="kys-highlight-label">Maddeler / Sayfa</span>
                  <span className="kys-highlight-value font-mono">
                    {detail.sections?.length || 0} Madde {detail.page_count ? `· ${detail.page_count} Sayfa` : ''}
                  </span>
                </div>
              </div>
            </div>

            {/* Warning banners */}
            {detail.warnings && detail.warnings.length > 0 && (
              <div className="kys-doc-warnings">
                {detail.warnings.map((w, idx) => (
                  <div key={idx} className="kys-warning-item">
                    <AlertTriangle size={14} className="text-warn shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* KYS Tabs Navigation */}
          <div className="kys-detail-tabs-bar" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'content'}
              className={`kys-tab-btn ${activeTab === 'content' ? 'active' : ''}`}
              onClick={() => setActiveTab('content')}
            >
              <FileText size={15} />
              <span>Doküman Maddeleri & Atıflar</span>
              <span className="kys-tab-count font-mono">{detail.sections?.length || 0}</span>
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'conflicts'}
              className={`kys-tab-btn ${activeTab === 'conflicts' ? 'active danger-tab' : ''}`}
              onClick={() => setActiveTab('conflicts')}
            >
              <ShieldAlert size={15} className={conflictFindings.length > 0 ? 'text-danger' : ''} />
              <span>Çelişen Noktalar (Çakışmalar)</span>
              {conflictFindings.length > 0 ? (
                <span className="kys-tab-count danger font-mono">{conflictFindings.length}</span>
              ) : (
                <span className="kys-tab-count ok font-mono">0</span>
              )}
            </button>

            <button
              type="button"
              role="tab"
              aria-selected={activeTab === 'gaps'}
              className={`kys-tab-btn ${activeTab === 'gaps' ? 'active warn-tab' : ''}`}
              onClick={() => setActiveTab('gaps')}
            >
              <AlertTriangle size={15} className={gapFindings.length > 0 ? 'text-warn' : ''} />
              <span>Açık Noktalar & İyileştirme Önerileri</span>
              {gapFindings.length > 0 ? (
                <span className="kys-tab-count warn font-mono">{gapFindings.length}</span>
              ) : (
                <span className="kys-tab-count ok font-mono">0</span>
              )}
            </button>
          </div>

          {/* TAB 1: Document Content & References */}
          {activeTab === 'content' && (
            <div className="kys-tab-pane">
              {/* References Panel */}
              {(detail.references?.length > 0 || detail.referenced_by?.length > 0) && (
                <div className="kys-panel-card kys-refs-grid">
                  {detail.references?.length > 0 && (
                    <div className="kys-ref-column">
                      <h3 className="kys-section-title">
                        <Link2 size={14} className="text-accent" />
                        <span>Bu Dokümanın Atıf Yaptığı Belgeler (Giden)</span>
                      </h3>
                      <div className="kys-ref-list">
                        {detail.references.map((ref, idx) => (
                          <div key={idx} className="kys-ref-item">
                            <button
                              type="button"
                              className="kys-ref-link font-mono"
                              onClick={() => onOpenDoc(ref.target_code || ref.ref_code)}
                            >
                              {ref.target_code || ref.ref_code}
                            </button>
                            <span className="kys-ref-title">
                              {ref.target_title || 'Başlık mevcut değil'}
                            </span>
                            {ref.target_status && (
                              <span
                                className={`kys-status-label mini ${ref.target_status.toLowerCase()}`}
                              >
                                {ref.target_status}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.referenced_by?.length > 0 && (
                    <div className="kys-ref-column">
                      <h3 className="kys-section-title">
                        <Link2 size={14} className="text-accent" />
                        <span>Bu Dokümana Atıf Yapan Belgeler (Gelen)</span>
                      </h3>
                      <div className="kys-ref-list">
                        {detail.referenced_by.map((ref, idx) => (
                          <div key={idx} className="kys-ref-item">
                            <button
                              type="button"
                              className="kys-ref-link font-mono"
                              onClick={() => onOpenDoc(ref.code)}
                            >
                              {ref.code}
                            </button>
                            <span className="kys-ref-title">{ref.title}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Sections / Clauses */}
              <div className="kys-panel-card">
                <div className="kys-panel-card-header">
                  <h3 className="kys-section-title">
                    <FileText size={15} className="text-accent" />
                    <span>Doküman Maddeleri ve Metin İçeriği ({detail.sections?.length || 0})</span>
                  </h3>
                </div>

                {detail.sections?.length === 0 ? (
                  <p className="kys-empty-sub">Bu doküman için henüz ayrıştırılmış madde bulunmuyor.</p>
                ) : (
                  <div className="kys-sections-list">
                    {detail.sections.map((sec, idx) => (
                      <article key={sec.id || idx} className="kys-section-row">
                        <div className="kys-section-meta font-mono">
                          <span className="kys-clause-badge">
                            {sec.clause_no ? `Madde ${sec.clause_no}` : `Bölüm ${idx + 1}`}
                          </span>
                          {sec.page !== undefined && sec.page !== null && (
                            <button
                              type="button"
                              className="kys-page-link"
                              onClick={() => loadPageImage(sec.page as number)}
                              title="Sayfa PDF görüntüsünü aç"
                            >
                              <ImageIcon size={12} />
                              <span>S. {sec.page}</span>
                            </button>
                          )}
                        </div>

                        <div className="kys-section-body">
                          {sec.heading && <h4 className="kys-section-heading">{sec.heading}</h4>}
                          <p className="kys-section-text">{sec.text}</p>
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </div>

              {/* Extracted KYS Rules */}
              {rules.length > 0 && (
                <div className="kys-panel-card">
                  <div className="kys-panel-card-header">
                    <h3 className="kys-section-title">
                      <Sparkles size={15} className="text-accent" />
                      <span>Bu Dokümandan Çıkarılan KYS Kuralları ({rules.length})</span>
                    </h3>
                  </div>
                  <div className="kys-sections-list">
                    {rules.map((r) => (
                      <div key={r.id} className="kys-section-row">
                        <div className="kys-section-meta font-mono">
                          <span className="kys-clause-badge">{r.rule_type}</span>
                          <span className="kys-status-label mini yururlukte">{r.status}</span>
                        </div>
                        <div className="kys-section-body">
                          <p className="kys-section-text">
                            <strong>{r.subject}</strong> — {r.action} {r.object}
                          </p>
                          {r.condition && (
                            <p className="kys-doc-summary-hint" style={{ marginTop: 4 }}>
                              Koşul: {r.condition}
                            </p>
                          )}
                          {r.source?.quote && (
                            <p className="kys-evidence-quote" style={{ marginTop: 6 }}>
                              "{r.source.quote}"
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* PDF Preview Modal / Drawer */}
              {previewPage !== null && (
                <div className="kys-preview-drawer">
                  <div className="kys-drawer-header">
                    <h4>
                      Sayfa Önizleme: {code} — Sayfa {previewPage}
                    </h4>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => setPreviewPage(null)}
                      title="Kapat"
                    >
                      <X size={15} />
                    </button>
                  </div>
                  <div className="kys-drawer-body">
                    {imageLoading && <p className="text-muted">Sayfa yükleniyor...</p>}
                    {imageError && <p className="text-danger">{imageError}</p>}
                    {imageUrl && (
                      <img
                        src={imageUrl}
                        alt={`Sayfa ${previewPage}`}
                        className="kys-preview-img"
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Conflicting Points (Çakışmalar - "Kanıtsız bulgu yok") */}
          {activeTab === 'conflicts' && (
            <div className="kys-tab-pane">
              <div className="kys-info-box">
                <Info size={16} className="text-accent shrink-0" />
                <p>
                  <strong>Kanıtsız bulgu gösterilmez:</strong> Aşağıdaki kural çelişkileri, bu
                  dokümanın maddeleri ile diğer KYS prosedür/talimatları arasındaki sayısal eşik,
                  yetki veya süre uyumsuzluklarını birebir kaynak alıntısıyla belgeler.
                </p>
              </div>

              {conflictFindings.length === 0 ? (
                <div className="kys-clean-state-card">
                  <CheckCircle2 size={32} className="text-ok" />
                  <h4>Bu Dokümanda Tespit Edilmiş Kural Çelişkisi Bulunmuyor</h4>
                  <p>
                    Tüm maddeler, yürürlükteki diğer dokümanlar ve onaylanmış KYS kuralları ile tam
                    uyum içerisindedir.
                  </p>
                </div>
              ) : (
                <div className="kys-conflicts-list">
                  {conflictFindings.map((finding) => (
                    <div
                      key={finding.id}
                      className={`kys-conflict-card severity-${finding.severity.toLowerCase()}`}
                    >
                      {/* Conflict Header */}
                      <div className="kys-conflict-card-header">
                        <div className="kys-conflict-title-row">
                          <span className={`kys-severity-tag ${finding.severity.toLowerCase()}`}>
                            {finding.severity === 'KRITIK'
                              ? 'KRİTİK ÇELİŞKİ'
                              : finding.severity === 'ORTA'
                              ? 'ORTA DÜZEY ÇELİŞKİ'
                              : 'DÜŞÜK ÇELİŞKİ'}
                          </span>
                          <span className="kys-finding-type-tag">
                            {finding.finding_type === 'CAKISMA'
                              ? 'Kural Çakışması'
                              : finding.finding_type === 'YETKI_ASIMI'
                              ? 'Yetki Uyuşmazlığı'
                              : 'Belirsizlik'}
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
                        <h4 className="kys-conflict-title">{finding.title}</h4>
                      </div>

                      {/* Conflict Description & Grounding */}
                      <p className="kys-conflict-desc">{finding.description}</p>

                      {/* Side-by-Side Evidence Comparison Box ("Kanıtsız Bulgu Yok") */}
                      <div className="kys-evidence-comparison">
                        {/* Left Side: This Document */}
                        <div className="kys-evidence-side current-doc">
                          <div className="kys-evidence-side-header">
                            <span className="kys-evidence-doc-label font-mono">
                              Bu Doküman: {code}
                            </span>
                            <span className="kys-evidence-tag">Kaynak Metin</span>
                          </div>
                          <div className="kys-evidence-quote-box">
                            <p className="kys-evidence-quote">
                              "{finding.evidence_quote || 'Dokümandaki ilgili madde hükmü'}"
                            </p>
                          </div>
                        </div>

                        {/* Middle VS Badge */}
                        <div className="kys-evidence-vs">
                          <Scale size={16} />
                          <span>VS</span>
                        </div>

                        {/* Right Side: Conflicting Rule / Target */}
                        <div className="kys-evidence-side clash-doc">
                          <div className="kys-evidence-side-header">
                            <span className="kys-evidence-doc-label font-mono">
                              Çelişen Doküman / Standart
                            </span>
                            <span className="kys-evidence-tag clash">Uyuşmazlık</span>
                          </div>
                          <div className="kys-evidence-quote-box clash">
                            <p className="kys-evidence-quote">
                              {finding.description}
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* Solution / Alignment Recommendation */}
                      <div className="kys-suggestion-box">
                        <div className="kys-suggestion-header">
                          <Sparkles size={14} className="text-accent" />
                          <span>KYS Çözüm & Hizalama Önerisi:</span>
                        </div>
                        <p className="kys-suggestion-text">
                          {generateActionableSuggestion(finding)}
                        </p>
                      </div>

                      {/* Action Bar */}
                      <div className="kys-finding-action-row">
                        <span className="text-muted text-xs">Durum Değiştir:</span>
                        <button
                          type="button"
                          className="kys-action-chip ok"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'COZULDU')}
                        >
                          <Check size={12} />
                          <span>Çözüldü Olarak İşaretle</span>
                        </button>

                        <button
                          type="button"
                          className="kys-action-chip accept"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'KABUL')}
                        >
                          <span>Kabul Edildi</span>
                        </button>

                        <button
                          type="button"
                          className="kys-action-chip dismiss"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'YANLIS_POZITIF')}
                        >
                          <X size={12} />
                          <span>Yanlış Pozitif</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Gaps & Actionable Recommendations */}
          {activeTab === 'gaps' && (
            <div className="kys-tab-pane">
              <div className="kys-info-box">
                <Info size={16} className="text-accent shrink-0" />
                <p>
                  <strong>Açık Kalan Noktalar:</strong> Dokümanda eksik bırakılmış onay adımları,
                  tanımsız roller, süreç boşlukları veya iptal edilen referansları içerir. Her açık
                  nokta için KYS denetim standardına uygun somut revizyon önerisi sunulmuştur.
                </p>
              </div>

              {gapFindings.length === 0 ? (
                <div className="kys-clean-state-card">
                  <CheckCircle2 size={32} className="text-ok" />
                  <h4>Açık Kalan Süreç veya Yetki Noktası Bulunmuyor</h4>
                  <p>
                    Doküman içerisinde onay zincirleri tam, rol tanımları eksiksiz ve yürürlükteki
                    atıflar günceldir.
                  </p>
                </div>
              ) : (
                <div className="kys-gaps-list">
                  {gapFindings.map((finding) => (
                    <div
                      key={finding.id}
                      className={`kys-gap-card severity-${finding.severity.toLowerCase()}`}
                    >
                      {/* Gap Header */}
                      <div className="kys-gap-card-header">
                        <div className="kys-conflict-title-row">
                          <span className={`kys-severity-tag ${finding.severity.toLowerCase()}`}>
                            {finding.severity}
                          </span>
                          <span className="kys-finding-type-tag gap">
                            {finding.finding_type === 'BOSLUK'
                              ? 'Süreç / Rol Boşluğu'
                              : finding.finding_type === 'EKSIK_ONAY'
                              ? 'Eksik Onaycı / Adım'
                              : finding.finding_type === 'GUNCELLIK'
                              ? 'İptal Forma Atıf'
                              : 'KYS Uyumsuzluğu'}
                          </span>
                          <span className={`kys-status-label mini ${finding.status.toLowerCase()}`}>
                            {finding.status}
                          </span>
                        </div>
                        <h4 className="kys-gap-title">{finding.title}</h4>
                      </div>

                      {/* Finding Details */}
                      <p className="kys-gap-desc">{finding.description}</p>

                      {/* Evidence */}
                      {finding.evidence_quote && (
                        <div className="kys-gap-evidence-box">
                          <span className="kys-gap-evidence-label">Tespit Edilen Madde Metni:</span>
                          <p className="kys-gap-evidence-quote">"{finding.evidence_quote}"</p>
                        </div>
                      )}

                      {/* Actionable KYS Recommendation (Öneri) */}
                      <div className="kys-actionable-proposal-box">
                        <div className="kys-proposal-header">
                          <Sparkles size={15} className="text-accent" />
                          <span className="kys-proposal-title">
                            Önerilen KYS Revizyon Formülasyonu:
                          </span>
                        </div>
                        <div className="kys-proposal-content">
                          <p className="kys-proposal-text">
                            {generateActionableSuggestion(finding)}
                          </p>
                        </div>
                      </div>

                      {/* Action Bar */}
                      <div className="kys-finding-action-row">
                        <span className="text-muted text-xs">Durum Değiştir:</span>
                        <button
                          type="button"
                          className="kys-action-chip ok"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'COZULDU')}
                        >
                          <Check size={12} />
                          <span>Açık Noktayı Kapat (Çözüldü)</span>
                        </button>

                        <button
                          type="button"
                          className="kys-action-chip accept"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'KABUL')}
                        >
                          <span>Revizyon Planına Al</span>
                        </button>

                        <button
                          type="button"
                          className="kys-action-chip dismiss"
                          disabled={updatingFindingId === finding.id}
                          onClick={() => handleUpdateFindingStatus(finding.id, 'YANLIS_POZITIF')}
                        >
                          <X size={12} />
                          <span>Göz Ardı Et</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
