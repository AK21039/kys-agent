import React, { useState } from 'react';
import { kysApi } from '../services/apiClient';
import { AskResponse } from '../types/kys';
import { Send, CheckCircle2, AlertCircle, ShieldAlert, BookOpen, Sparkles, HelpCircle } from 'lucide-react';

interface AskTabProps {
  onOpenDoc: (code: string) => void;
}

const SAMPLE_QUESTIONS = [
  'Yıllık iç tetkik planı ne zaman ve kim tarafından hazırlanır?',
  'Düzeltici faaliyet talebini kimler başlatabilir ve onay makamı kimdir?',
  'Yönetimin gözden geçirmesi toplantısı hangi periyotlarla yapılır?',
  'Satın alma onay limitleri ve yetki matrisi nasıldır?',
];

export const AskTab: React.FC<AskTabProps> = ({ onOpenDoc }) => {
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAsk = async (qText?: string) => {
    const targetQ = (qText !== undefined ? qText : question).trim();
    if (!targetQ) return;

    if (qText !== undefined) {
      setQuestion(targetQ);
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const data = await kysApi.ask(targetQ);
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Soru yanıtlama sırasında bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <Sparkles size={18} color="var(--accent)" />
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
            KYS Kaynaklı Soru Asistanı
          </h2>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 14px 0' }}>
          Yalnızca yürürlükteki Kalite Yönetim Sistemi dokümanlarına ve doğrulanmış kurallara dayanarak yanıt verir.
          Tüm yanıtlar birebir doküman ve madde alıntılarıyla kanıtlandırılır.
        </p>

        <form
          className="search-form"
          onSubmit={(e) => {
            e.preventDefault();
            handleAsk();
          }}
        >
          <input
            type="text"
            placeholder="KYS ile ilgili sorunuzu yazın... (Örn: İç tetkik raporlama süresi nedir?)"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="primary" disabled={loading || !question.trim()}>
            {loading ? (
              'İnceleniyor...'
            ) : (
              <>
                <Send size={16} />
                <span>Sor</span>
              </>
            )}
          </button>
        </form>

        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: 6 }}>
            Örnek Sorular:
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {SAMPLE_QUESTIONS.map((sq, idx) => (
              <button
                key={idx}
                type="button"
                className="icon-btn"
                style={{ fontSize: '12px', padding: '4px 10px', borderRadius: '16px' }}
                onClick={() => handleAsk(sq)}
                disabled={loading}
              >
                <HelpCircle size={12} color="var(--accent)" />
                {sq}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderLeft: '4px solid var(--danger)', backgroundColor: 'var(--danger-soft)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--danger)', fontWeight: 600 }}>
            <AlertCircle size={18} />
            <span>Hata Oluştu</span>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: '13.5px', color: 'var(--text)' }}>{error}</p>
        </div>
      )}

      {result && (
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <BookOpen size={18} color="var(--accent)" />
                <h3 style={{ margin: 0, fontSize: '16px' }}>Cevap</h3>
              </div>
              {result.yeterli_bilgi ? (
                <span className="badge badge-ok">
                  <CheckCircle2 size={12} />
                  Yeterli KYS Bilgisi Mevcut
                </span>
              ) : (
                <span className="badge badge-warn">
                  <AlertCircle size={12} />
                  Kısmi / Yetersiz Bilgi
                </span>
              )}
            </div>

            <div className="answer-box">
              {result.answer || 'Cevap bulunamadı.'}
            </div>
          </div>

          <div className="card">
            <h3 style={{ margin: '0 0 12px 0', fontSize: '15px', fontWeight: 600 }}>
              Kaynak Alıntıları ({result.citations?.length || 0})
            </h3>

            {(!result.citations || result.citations.length === 0) ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '13.5px', margin: 0 }}>
                Bu yanıt için doğrudan alıntı kaynağı dönmedi.
              </p>
            ) : (
              <div className="citations-list">
                {result.citations.map((cite, idx) => {
                  const isVerified = cite.verified !== false;
                  return (
                    <div
                      key={idx}
                      className="citation-card"
                      style={{
                        borderLeft: `4px solid ${isVerified ? 'var(--ok)' : 'var(--danger)'}`,
                      }}
                    >
                      <div className="citation-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <span
                            className="ref-link"
                            onClick={() => onOpenDoc(cite.doc_code)}
                            title="Doküman ayrıntısına git"
                          >
                            {cite.doc_code}
                          </span>
                          {cite.revision && (
                            <span className="badge badge-gray">Rev: {cite.revision}</span>
                          )}
                          {cite.clause_no && (
                            <span className="badge badge-info">Md. {cite.clause_no}</span>
                          )}
                          {cite.heading && (
                            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
                              ({cite.heading})
                            </span>
                          )}
                        </div>

                        <div>
                          {isVerified ? (
                            <span className="badge badge-ok" title="Metin kaynak dokümanla birebir eşleşti">
                              <CheckCircle2 size={12} />
                              Doğrulandı
                            </span>
                          ) : (
                            <span
                              className="badge badge-danger"
                              title="Alıntı kaynak metinle tam uyuşmuyor veya bulunamadı"
                            >
                              <ShieldAlert size={12} />
                              Doğrulanamadı
                            </span>
                          )}
                        </div>
                      </div>

                      {cite.quote && (
                        <div className={`quote-box ${!isVerified ? 'quote-unverified' : ''}`}>
                          "{cite.quote}"
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
