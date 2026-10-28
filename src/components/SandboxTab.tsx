import React, { useState } from 'react';
import { kysApi } from '../services/apiClient';
import { ComplianceCheckResponse } from '../types/kys';
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  UserCheck,
  ClipboardList,
  Sparkles,
  ArrowRight,
  Send,
  HelpCircle,
} from 'lucide-react';

interface SandboxTabProps {
  onOpenDoc: (code: string) => void;
}

const SAMPLE_SCENARIOS = [
  {
    title: 'Acil Doğrudan Temin',
    text: 'Üretim hattındaki kritik arıza nedeniyle 150.000 TL tutarındaki yedek parçanın acil doğrudan temin yoluyla tek kaynaktan alınması planlanıyor.',
    dept: 'Satınalma',
    budget: 150000,
  },
  {
    title: 'Yeni Tedarikçi Onayı',
    text: 'Yurtdışından yeni bir hammadde tedarikçisi ile çalışılacak. Kalite denetimi yapılmadan ilk parti siparişin açılması talep ediliyor.',
    dept: 'Kalite Güvence',
    budget: 50000,
  },
  {
    title: 'Prosedür Dışı İşe Alım',
    text: 'Acil yazılım projesi için bütçe onay süreci tamamlanmadan 2 adet harici danışmanın sözleşmeli olarak başlatılması isteniyor.',
    dept: 'İnsan Kaynakları',
    budget: 80000,
  },
];

export const SandboxTab: React.FC<SandboxTabProps> = ({ onOpenDoc }) => {
  const [taskDesc, setTaskDesc] = useState<string>('');
  const [department, setDepartment] = useState<string>('');
  const [budget, setBudget] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<ComplianceCheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleCheck = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!taskDesc.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await kysApi.checkCompliance({
        task_description: taskDesc.trim(),
        department: department.trim() || undefined,
        budget: budget ? parseFloat(budget) : undefined,
      });
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Uygunluk denetimi yapılamadı');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadSample = (s: typeof SAMPLE_SCENARIOS[0]) => {
    setTaskDesc(s.text);
    setDepartment(s.dept);
    setBudget(String(s.budget));
  };

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <Sparkles size={20} color="var(--accent)" />
          <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
            KYS Uygunluk Kum Havuzu (Ajan 3.1)
          </h2>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 16px 0' }}>
          Planladığınız bir işi, satınalmayı veya operasyonel kararı uygulamaya almadan önce simüle edin.
          Ajan 3.1 KYS prosedürlerini, onay kurallarını ve yetki matrisini tarayarak anında uygunluk raporu üretir.
        </p>

        <form onSubmit={handleCheck} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: 6 }}>
              Planlanan İş / Karar Açıklaması
            </label>
            <textarea
              rows={4}
              placeholder="Yapılması planlanan işi, yöntemi ve gerekçeyi detaylıca açıklayın... (Örn: 200.000 TL tutarlı doğrudan temin yapılacak...)"
              value={taskDesc}
              onChange={(e) => setTaskDesc(e.target.value)}
              required
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label style={{ display: 'block', fontSize: '12.5px', color: 'var(--text-muted)', marginBottom: 4 }}>
                İlgili Birim / Departman (Opsiyonel)
              </label>
              <input
                type="text"
                placeholder="Örn: Satınalma, Üretim, Bakım"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12.5px', color: 'var(--text-muted)', marginBottom: 4 }}>
                Bütçe / Tutar (TL, Opsiyonel)
              </label>
              <input
                type="number"
                placeholder="Örn: 150000"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
              />
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Örnek Senaryolar:</span>
              {SAMPLE_SCENARIOS.map((sample, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="icon-btn"
                  style={{ fontSize: '11.5px', padding: '3px 8px', borderRadius: '12px' }}
                  onClick={() => handleLoadSample(sample)}
                  disabled={loading}
                >
                  <HelpCircle size={11} color="var(--accent)" />
                  {sample.title}
                </button>
              ))}
            </div>

            <button type="submit" className="primary" disabled={loading || !taskDesc.trim()}>
              {loading ? (
                'KYS İnceleniyor...'
              ) : (
                <>
                  <Send size={15} />
                  <span>Uygunluğu Denetle</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <XCircle size={18} />
            <span>Denetim Hatası</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {/* Result Display */}
      {result && (
        <div>
          {/* Verdict Card */}
          <div
            className="card"
            style={{
              borderLeft: `6px solid ${
                result.verdict === 'UYGUN'
                  ? 'var(--ok)'
                  : result.verdict === 'SARTLI_UYGUN'
                  ? 'var(--warn)'
                  : 'var(--danger)'
              }`,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {result.verdict === 'UYGUN' ? (
                  <CheckCircle2 size={24} color="var(--ok)" />
                ) : result.verdict === 'SARTLI_UYGUN' ? (
                  <AlertTriangle size={24} color="var(--warn)" />
                ) : (
                  <XCircle size={24} color="var(--danger)" />
                )}

                <div>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>
                    {result.verdict === 'UYGUN'
                      ? 'KYS Prosedürlerine UYGUN'
                      : result.verdict === 'SARTLI_UYGUN'
                      ? 'ŞARTLI UYGUN (Ek Onay/Şart Gerekir)'
                      : 'KYS Prosedürlerine UYGUN DEĞİL'}
                  </h3>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    {result.model && `Denetçi: ${result.model}`}
                  </div>
                </div>
              </div>

              <span
                className={`badge ${
                  result.verdict === 'UYGUN'
                    ? 'badge-ok'
                    : result.verdict === 'SARTLI_UYGUN'
                    ? 'badge-warn'
                    : 'badge-danger'
                }`}
                style={{ fontSize: '13px', padding: '4px 10px' }}
              >
                {result.verdict}
              </span>
            </div>

            <div className="answer-box" style={{ margin: '8px 0 0' }}>
              {result.summary}
            </div>
          </div>

          {/* Grid: Approvals, Forms, Steps */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14, marginBottom: 14 }}>
            {/* Required Approvals */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <UserCheck size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Zorunlu Onay Makamları ({result.required_approvals?.length || 0})
                </h4>
              </div>

              {(!result.required_approvals || result.required_approvals.length === 0) ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Özel bir onay makamı zorunluluğu tespit edilmedi.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {result.required_approvals.map((app, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        backgroundColor: 'var(--panel-hover)',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ fontWeight: 700, color: 'var(--text)' }}>{app.role}</div>
                      {app.condition && (
                        <div style={{ fontSize: '12px', color: 'var(--warn)', marginTop: 2 }}>
                          Şart: {app.condition}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Required Forms */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <ClipboardList size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Zorunlu Formlar & Kayıtlar ({result.required_forms?.length || 0})
                </h4>
              </div>

              {(!result.required_forms || result.required_forms.length === 0) ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: 0 }}>
                  Doldurulması gereken özel bir form kaydı bulunmuyor.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {result.required_forms.map((form, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 'var(--radius)',
                        border: '1px solid var(--line)',
                        backgroundColor: 'var(--panel-hover)',
                        fontSize: '13px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span
                        className="ref-link"
                        onClick={() => onOpenDoc(form.form_code)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
                      >
                        <FileText size={13} />
                        {form.form_code}
                      </span>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {form.form_name}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Required Steps */}
          {result.required_steps && result.required_steps.length > 0 && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <ArrowRight size={16} color="var(--accent)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>İzlenmesi Gereken Adımlar</h4>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {result.required_steps.map((step, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 8,
                      fontSize: '13.5px',
                    }}
                  >
                    <span
                      style={{
                        width: 20,
                        height: 20,
                        borderRadius: '50%',
                        backgroundColor: 'var(--accent)',
                        color: '#fff',
                        display: 'inline-flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '11px',
                        fontWeight: 700,
                        flexShrink: 0,
                        marginTop: 1,
                      }}
                    >
                      {idx + 1}
                    </span>
                    <span>{step}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Citations & Evidence */}
          {result.citations && result.citations.length > 0 && (
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <ShieldCheck size={16} color="var(--ok)" />
                <h4 style={{ margin: 0, fontSize: '14.5px' }}>
                  Dayanak Doküman ve Kanıt Alıntıları ({result.citations.length})
                </h4>
              </div>

              <div className="citations-list">
                {result.citations.map((cite, idx) => (
                  <div key={idx} className="citation-card">
                    <div className="citation-header">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span
                          className="ref-link"
                          onClick={() => onOpenDoc(cite.doc_code)}
                        >
                          {cite.doc_code}
                        </span>
                        {cite.revision && <span className="badge badge-gray">Rev: {cite.revision}</span>}
                        {cite.clause_no && <span className="badge badge-info">Md. {cite.clause_no}</span>}
                      </div>

                      <span className="badge badge-ok">Doğrulandı</span>
                    </div>

                    <div className="quote-box">"{cite.quote}"</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
