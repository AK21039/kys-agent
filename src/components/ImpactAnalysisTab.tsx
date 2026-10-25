import React, { useState, useEffect } from 'react';
import { kysApi } from '../services/apiClient';
import { ImpactAnalysisResponse } from '../types/kys';
import {
  GitPullRequest,
  AlertOctagon,
  FileText,
  GitBranch,
  ShieldCheck,
  Users,
  Search,
  Download,
  ArrowRight,
} from 'lucide-react';

interface ImpactAnalysisTabProps {
  initialDocCode?: string | null;
  onOpenDoc: (code: string) => void;
}

export const ImpactAnalysisTab: React.FC<ImpactAnalysisTabProps> = ({
  initialDocCode,
  onOpenDoc,
}) => {
  const [docCode, setDocCode] = useState<string>(initialDocCode || '');
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<ImpactAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async (targetCode?: string) => {
    const code = (targetCode || docCode).trim();
    if (!code) return;

    if (targetCode) setDocCode(targetCode);

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await kysApi.getImpactAnalysis(code);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Etki analizi yapılamadı');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialDocCode) {
      handleAnalyze(initialDocCode);
    }
  }, [initialDocCode]);

  const handleExportCsv = () => {
    if (!result) return;

    const rows: string[] = [];
    rows.push(`"KYS Revizyon Etki Analizi Raporu - ${result.document_code}"`);
    rows.push(`"Doküman:","${result.document_code} - ${result.title} (Rev: ${result.revision})"`);
    rows.push(`"Risk Düzeyi:","${result.risk_level}"`);
    rows.push(`"Özet:","${result.summary}"`);
    rows.push('');

    rows.push('"1. ETKİLENEN DOKÜMANLAR"');
    rows.push('"Kod","Başlık","Atıf Yapılan Madde"');
    result.affected_documents.forEach((d) => {
      rows.push(`"${d.code}","${d.title}","${d.clause_referenced || '-'}"`);
    });
    rows.push('');

    rows.push('"2. ETKİLENEN SÜREÇLER VE ADIMLAR"');
    rows.push('"Süreç Kodu","Süreç Adı","Adım No","Adım Adı"');
    result.affected_processes.forEach((p) => {
      rows.push(`"${p.process_code}","${p.process_name}","${p.step_seq}","${p.step_name}"`);
    });
    rows.push('');

    rows.push('"3. ETKİLENEN KURAL VE ONAYLAR"');
    rows.push('"Kural ID","Tip","Özne (Rol)","Eylem","Nesne"');
    result.affected_rules.forEach((r) => {
      rows.push(`"${r.id}","${r.rule_type}","${r.subject}","${r.action}","${r.object}"`);
    });
    rows.push('');

    rows.push('"4. ETKİLENEN KARAR VE YETKİLER (RACI)"');
    rows.push('"Karar ID","Konu","Karar Sahibi (A)","Sorumlu (R)"');
    result.affected_decisions.forEach((dec) => {
      rows.push(`"${dec.id}","${dec.topic}","${dec.decision_maker}","${dec.responsible || '-'}"`);
    });

    const csvContent = '\uFEFF' + rows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `KYS_Etki_Analizi_${result.document_code}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <GitPullRequest size={20} color="var(--accent)" />
          <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
            KYS Revizyon Etki Analizi (Faz 4)
          </h2>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 16px 0' }}>
          Bir doküman güncellendiğinde veya iptal edildiğinde zincirleme olarak hangi prosedürlerin, süreç adımlarının, onay kurallarının ve RACI yetkilerinin etkileneceğini grafiksel ve yapısal olarak inceleyin.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleAnalyze();
          }}
          style={{ display: 'flex', gap: 10 }}
        >
          <input
            type="text"
            placeholder="Analiz edilecek doküman kodunu girin (Örn: PR-04, PR-01, TL-02)..."
            value={docCode}
            onChange={(e) => setDocCode(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="primary" disabled={loading || !docCode.trim()}>
            {loading ? (
              'Analiz Ediliyor...'
            ) : (
              <>
                <Search size={15} />
                <span>Etkiyi Analiz Et</span>
              </>
            )}
          </button>
        </form>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertOctagon size={18} />
            <span>Etki Analizi Hatası</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {result && (
        <div>
          {/* Header & Risk Level */}
          <div
            className="card"
            style={{
              borderLeft: `6px solid ${
                result.risk_level === 'YUKSEK'
                  ? 'var(--danger)'
                  : result.risk_level === 'ORTA'
                  ? 'var(--warn)'
                  : 'var(--ok)'
              }`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>
                    {result.document_code}
                  </h3>
                  <span className="badge badge-gray">Rev: {result.revision}</span>
                  <span
                    className={`badge ${
                      result.risk_level === 'YUKSEK'
                        ? 'badge-danger'
                        : result.risk_level === 'ORTA'
                        ? 'badge-warn'
                        : 'badge-ok'
                    }`}
                    style={{ fontSize: '12.5px', padding: '3px 8px' }}
                  >
                    Risk Düzeyi: {result.risk_level}
                  </span>
                </div>
                <div style={{ fontSize: '14.5px', color: 'var(--text-muted)', marginTop: 4 }}>
                  {result.title}
                </div>
              </div>

              <button
                type="button"
                className="icon-btn"
                onClick={handleExportCsv}
                title="Raporu CSV olarak indir"
              >
                <Download size={15} />
                <span>Raporu Dışa Aktar (CSV)</span>
              </button>
            </div>

            <div className="answer-box" style={{ margin: '0 0 14px 0' }}>
              <strong>Etki Değerlendirme Özeti:</strong> {result.summary}
            </div>

            {/* Summary Counters */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
              <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--panel-hover)', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <FileText size={13} color="var(--accent)" />
                  Atıf Yapan Doküman
                </div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{result.affected_documents.length}</div>
              </div>

              <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--panel-hover)', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <GitBranch size={13} color="var(--accent)" />
                  Etkilenen Süreç Adımı
                </div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{result.affected_processes.length}</div>
              </div>

              <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--panel-hover)', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <ShieldCheck size={13} color="var(--ok)" />
                  Dayanak Kural / Onay
                </div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{result.affected_rules.length}</div>
              </div>

              <div style={{ padding: '10px', borderRadius: 'var(--radius)', backgroundColor: 'var(--panel-hover)', border: '1px solid var(--line)' }}>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Users size={13} color="var(--warn)" />
                  RACI Karar Yetkisi
                </div>
                <div style={{ fontSize: '20px', fontWeight: 700 }}>{result.affected_decisions.length}</div>
              </div>
            </div>
          </div>

          {/* 4 Detailed Sections */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            {/* 1. Affected Documents */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <FileText size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Atıfta Bulunan Dokümanlar ({result.affected_documents.length})
                </h4>
              </div>

              {result.affected_documents.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümana atıfta bulunan başka bir doküman bulunamadı.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto' }}>
                  {result.affected_documents.map((d, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '13px',
                      }}
                    >
                      <div>
                        <span
                          className="ref-link"
                          onClick={() => onOpenDoc(d.code)}
                          style={{ fontWeight: 600 }}
                        >
                          {d.code}
                        </span>
                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{d.title}</div>
                      </div>
                      {d.clause_referenced && (
                        <span className="badge badge-info">Md. {d.clause_referenced}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 2. Affected Processes */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <GitBranch size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Etkilenen Süreçler & Adımlar ({result.affected_processes.length})
                </h4>
              </div>

              {result.affected_processes.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümana doğrudan bağlı bir süreç adımı bulunamadı.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto' }}>
                  {result.affected_processes.map((p, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="badge badge-info">{p.process_code}</span>
                        <span style={{ fontWeight: 600 }}>{p.process_name}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <ArrowRight size={12} color="var(--accent)" />
                        <strong>Adım {p.step_seq}:</strong> {p.step_name}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 3. Affected Rules */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <ShieldCheck size={16} color="var(--ok)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Etkilenen Kurallar & Onaylar ({result.affected_rules.length})
                </h4>
              </div>

              {result.affected_rules.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümandan türetilmiş aktif bir kural bulunamadı.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto' }}>
                  {result.affected_rules.map((r) => (
                    <div
                      key={r.id}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span className="badge badge-info" style={{ fontSize: '11px' }}>{r.rule_type}</span>
                        <span style={{ fontWeight: 600 }}>{r.subject}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {r.action} → {r.object}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 4. Affected Decisions (RACI) */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Users size={16} color="var(--warn)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Etkilenen RACI Kararları ({result.affected_decisions.length})
                </h4>
              </div>

              {result.affected_decisions.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Bu dokümandaki onay kurallarına dayanan karar envanteri maddesi tespit edilmedi.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflowY: 'auto' }}>
                  {result.affected_decisions.map((dec) => (
                    <div
                      key={dec.id}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{dec.topic}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: 2 }}>
                        <strong>Onaylayan (A):</strong> {dec.decision_maker}
                        {dec.responsible && ` | Sorumlu (R): ${dec.responsible}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
