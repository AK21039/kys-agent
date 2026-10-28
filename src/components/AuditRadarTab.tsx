import React, { useState, useEffect, useCallback } from 'react';
import { kysApi } from '../services/apiClient';
import { FindingItem, FindingStatus, FindingType, SeverityType } from '../types/kys';
import {
  ShieldAlert,
  AlertOctagon,
  AlertTriangle,
  Info,
  Play,
  RefreshCw,
  FileText,
  Filter,
  CheckCircle,
  XCircle,
  Check,
} from 'lucide-react';

interface AuditRadarTabProps {
  onOpenDoc: (code: string) => void;
  onStatsChanged?: () => void;
}

const SEVERITIES: (SeverityType | 'HEPSI')[] = ['HEPSI', 'KRITIK', 'ORTA', 'DUSUK'];

const FINDING_TYPES: { value: FindingType | 'HEPSI'; label: string }[] = [
  { value: 'HEPSI', label: 'Tüm Bulgu Tipleri' },
  { value: 'CAKISMA', label: 'Kural Çakışması' },
  { value: 'BOSLUK', label: 'Süreç / Rol Boşluğu' },
  { value: 'GUNCELLIK', label: 'İptal Forma / Dokümana Atıf' },
  { value: 'YETKI_ASIMI', label: 'Yetki Aşımı / Karar Uyumsuzluğu' },
  { value: 'EKSIK_ONAY', label: 'Eksik Onaycı / Adım' },
  { value: 'UYGUNSUZLUK', label: 'Standart / KYS Uyumsuzluğu' },
  { value: 'BELIRSIZLIK', label: 'Belirsizlik / Tutarsız Eşik' },
];

const STATUSES: { value: FindingStatus | 'HEPSI'; label: string }[] = [
  { value: 'ACIK', label: 'Açık Bulgular' },
  { value: 'KABUL', label: 'Kabul Edildi' },
  { value: 'YANLIS_POZITIF', label: 'Yanlış Pozitif' },
  { value: 'COZULDU', label: 'Çözüldü' },
  { value: 'HEPSI', label: 'Tümü' },
];

export const AuditRadarTab: React.FC<AuditRadarTabProps> = ({ onOpenDoc, onStatsChanged }) => {
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [runningAnalysis, setRunningAnalysis] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<FindingStatus | 'HEPSI'>('ACIK');
  const [severityFilter, setSeverityFilter] = useState<SeverityType | 'HEPSI'>('HEPSI');
  const [typeFilter, setTypeFilter] = useState<FindingType | 'HEPSI'>('HEPSI');

  // Action loading
  const [actionId, setActionId] = useState<number | null>(null);

  const fetchFindings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await kysApi.getFindings({
        status: statusFilter,
        severity: severityFilter,
        finding_type: typeFilter,
      });
      setFindings(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Bulgular yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, severityFilter, typeFilter]);

  useEffect(() => {
    fetchFindings();
  }, [fetchFindings]);

  const handleRunAnalysis = async () => {
    setRunningAnalysis(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await kysApi.runAuditAnalysis();
      setSuccessMsg(
        `Denetim analizi tamamlandı! Toplam ${res.findings_count} bulgu tespit edildi (${res.critical_count} Kritik, ${res.medium_count} Orta, ${res.low_count} Düşük).`
      );
      fetchFindings();
      onStatsChanged?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Denetim analizi çalıştırılamadı');
    } finally {
      setRunningAnalysis(false);
    }
  };

  const handleUpdateStatus = async (id: number, newStatus: FindingStatus) => {
    setActionId(id);
    try {
      const updated = await kysApi.updateFindingStatus(id, newStatus);
      setFindings((prev) => prev.map((f) => (f.id === id ? updated : f)));
      onStatsChanged?.();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Durum güncellenemedi');
    } finally {
      setActionId(null);
    }
  };

  const criticalCount = findings.filter((f) => f.severity === 'KRITIK').length;
  const mediumCount = findings.filter((f) => f.severity === 'ORTA').length;
  const lowCount = findings.filter((f) => f.severity === 'DUSUK').length;

  return (
    <div>
      {/* Top Header Card */}
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ShieldAlert size={20} color="var(--danger)" />
            <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
              KYS Denetim Radarı (Faz 3)
            </h2>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              type="button"
              className="primary"
              onClick={handleRunAnalysis}
              disabled={runningAnalysis}
              style={{ fontSize: '13px', padding: '6px 14px' }}
            >
              <Play size={14} style={{ fill: '#fff' }} />
              <span>{runningAnalysis ? 'Analiz Çalışıyor...' : 'Tüm Sistemi Denetle'}</span>
            </button>

            <button
              type="button"
              className="icon-btn"
              onClick={fetchFindings}
              disabled={loading}
              title="Yenile"
            >
              <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
            </button>
          </div>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
          Deterministik SQL kontrolleri ve LLM yargıçlarıyla sistemdeki yetki aşımı, kural çakışması, iptal dokümanlara yapılan atıflar ve süreç boşluklarını izleyin.
        </p>

        {/* Counter Summary Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
          <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--panel-hover)', border: '1px solid var(--line)' }}>
            <div style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>Toplam Bulgu</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text)' }}>{findings.length}</div>
          </div>

          <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--danger-soft)', border: '1px solid var(--danger-border)' }}>
            <div style={{ fontSize: '11.5px', color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertOctagon size={13} />
              Kritik Bulgular
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--danger)' }}>{criticalCount}</div>
          </div>

          <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--warn-soft)', border: '1px solid var(--warn-border)' }}>
            <div style={{ fontSize: '11.5px', color: 'var(--warn)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <AlertTriangle size={13} />
              Orta Seviye
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--warn)' }}>{mediumCount}</div>
          </div>

          <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--accent-soft)', border: '1px solid var(--accent-border)' }}>
            <div style={{ fontSize: '11.5px', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Info size={13} />
              Düşük Seviye
            </div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--accent)' }}>{lowCount}</div>
          </div>
        </div>

        {/* Filters */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginTop: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
              <Filter size={12} style={{ display: 'inline', marginRight: 4 }} />
              Durum
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as FindingStatus | 'HEPSI')}
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
              Önem Derecesi
            </label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as SeverityType | 'HEPSI')}
            >
              {SEVERITIES.map((sev) => (
                <option key={sev} value={sev}>
                  {sev === 'HEPSI' ? 'Tümü' : sev}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-muted)', marginBottom: 4 }}>
              Bulgu Tipi
            </label>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as FindingType | 'HEPSI')}
            >
              {FINDING_TYPES.map((ft) => (
                <option key={ft.value} value={ft.value}>
                  {ft.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {successMsg && (
        <div className="card" style={{ backgroundColor: 'var(--ok-soft)', border: '1px solid var(--ok-border)', color: 'var(--ok)', padding: '12px 14px' }}>
          {successMsg}
        </div>
      )}

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertOctagon size={18} />
            <span>Hata</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {/* Findings List */}
      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Bulgular taranıyor...
        </div>
      ) : findings.length === 0 ? (
        <div className="card" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
          Bu filtreye uygun denetim bulgusu bulunamadı.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {findings.map((f) => {
            const isCritical = f.severity === 'KRITIK';
            const isMedium = f.severity === 'ORTA';
            const isActing = actionId === f.id;

            return (
              <div
                key={f.id}
                className="card"
                style={{
                  borderLeft: `5px solid ${
                    isCritical ? 'var(--danger)' : isMedium ? 'var(--warn)' : 'var(--accent)'
                  }`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span
                      className={`badge ${
                        isCritical ? 'badge-danger' : isMedium ? 'badge-warn' : 'badge-info'
                      }`}
                      style={{ fontWeight: 700 }}
                    >
                      {f.severity}
                    </span>
                    <span className="badge badge-gray">{f.finding_type}</span>
                    <span className={`badge ${f.status === 'COZULDU' ? 'badge-ok' : f.status === 'YANLIS_POZITIF' ? 'badge-gray' : 'badge-warn'}`}>
                      {f.status}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      #{f.id}
                    </span>
                  </div>

                  {/* Actions */}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => handleUpdateStatus(f.id, 'COZULDU')}
                      disabled={isActing || f.status === 'COZULDU'}
                      style={{ color: 'var(--ok)' }}
                      title="Çözüldü Olarak İşaretle"
                    >
                      <CheckCircle size={14} />
                      <span>Çözüldü</span>
                    </button>

                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => handleUpdateStatus(f.id, 'KABUL')}
                      disabled={isActing || f.status === 'KABUL'}
                      style={{ color: 'var(--warn)' }}
                      title="Riski Kabul Et"
                    >
                      <Check size={14} />
                      <span>Kabul Et</span>
                    </button>

                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => handleUpdateStatus(f.id, 'YANLIS_POZITIF')}
                      disabled={isActing || f.status === 'YANLIS_POZITIF'}
                      style={{ color: 'var(--text-muted)' }}
                      title="Yanlış Pozitif"
                    >
                      <XCircle size={14} />
                      <span>Yanlış Pozitif</span>
                    </button>
                  </div>
                </div>

                <h4 style={{ margin: '0 0 6px 0', fontSize: '15px', color: 'var(--text)' }}>
                  {f.title}
                </h4>

                <p style={{ margin: '0 0 10px 0', fontSize: '13.5px', lineHeight: 1.5, color: 'var(--text)' }}>
                  {f.description}
                </p>

                {/* Evidence / Source Link */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, paddingTop: 8, borderTop: '1px solid var(--line)' }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    {f.document_code && (
                      <span
                        className="ref-link"
                        onClick={() => onOpenDoc(f.document_code!)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '12.5px' }}
                      >
                        <FileText size={13} />
                        {f.document_code}
                      </span>
                    )}

                    {f.process_code && (
                      <span className="badge badge-gray" style={{ fontSize: '12px' }}>
                        Süreç: {f.process_code}
                      </span>
                    )}
                  </div>

                  {f.evidence_quote && (
                    <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', fontStyle: 'italic', maxWidth: '70%', textAlign: 'right' }}>
                      Kanıt: "{f.evidence_quote}"
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
