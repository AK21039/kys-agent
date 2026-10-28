import React, { useState, useEffect } from 'react';
import { kysApi, LlmSessionConfig } from '../services/apiClient';
import { AskResponse } from '../types/kys';
import {
  Send,
  CheckCircle2,
  AlertCircle,
  ShieldAlert,
  BookOpen,
  Sparkles,
  HelpCircle,
  KeyRound,
  Trash2,
  X,
  Cpu,
  Settings2,
} from 'lucide-react';

interface AskTabProps {
  onOpenDoc: (code: string) => void;
}

const SAMPLE_QUESTIONS = [
  'Yıllık iç tetkik planı ne zaman ve kim tarafından hazırlanır?',
  'Düzeltici faaliyet talebini kimler başlatabilir ve onay makamı kimdir?',
  'Yönetimin gözden geçirmesi toplantısı hangi periyotlarla yapılır?',
  'Satın alma onay limitleri ve yetki matrisi nasıldır?',
];

// 6. Cevaptaki "model" alanını rozet olarak göster
export const formatModelBadge = (modelStr?: string): string => {
  if (!modelStr) return '';
  const trimmed = modelStr.trim();
  if (trimmed === 'gemini:gemini-3.6-flash') return 'Gemini 3.6 Flash';
  if (trimmed === 'anthropic:claude-haiku-5-5') return 'Claude Haiku';
  // Bilinmeyen değeri olduğu gibi yaz
  return trimmed;
};

export const AskTab: React.FC<AskTabProps> = ({ onOpenDoc }) => {
  const [question, setQuestion] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Oturum LLM durumu (sessionStorage)
  const [sessionLlm, setSessionLlm] = useState<LlmSessionConfig | null>(() => kysApi.getLlmSessionConfig());

  // 503 MODEL_YOK durumunda açılacak anahtar modalı
  const [showKeyModal, setShowKeyModal] = useState<boolean>(false);
  const [modalDetail, setModalDetail] = useState<string>('');
  const [selectedProvider, setSelectedProvider] = useState<'gemini' | 'anthropic'>('gemini');
  const [inputKey, setInputKey] = useState<string>('');
  const [pendingQuestion, setPendingQuestion] = useState<string>('');

  // Sayfa yüklendiğinde mevcut oturum ayarlarını senkronize et
  useEffect(() => {
    setSessionLlm(kysApi.getLlmSessionConfig());
  }, []);

  const handleAsk = async (qText?: string, isRetryAfterKey: boolean = false) => {
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
      const anyErr = err as { isModelYok?: boolean; code?: string; detail?: string; message?: string };

      // 2. Anahtar kutusu YALNIZCA şu durumda açılır: HTTP 503 ve gövdede {"detail": "...", "code": "MODEL_YOK"}
      if (anyErr?.isModelYok || anyErr?.code === 'MODEL_YOK') {
        const detailText = anyErr.detail || anyErr.message || 'Sunucuda kullanılabilir bir model bulunamadı.';
        if (isRetryAfterKey) {
          // 4. Yine MODEL_YOK gelirse detail metnini göster, döngüye girme
          setError(detailText);
        } else {
          // İlk kez MODEL_YOK geldi: Anahtar modalını aç
          setPendingQuestion(targetQ);
          setModalDetail(detailText);
          setShowKeyModal(true);
        }
      } else {
        // Diğer hatalar (400, 404, 500 vb.) doğrudan hata mesajı olarak gösterilir
        setError(err instanceof Error ? err.message : 'Soru yanıtlama sırasında bir hata oluştu');
      }
    } finally {
      setLoading(false);
    }
  };

  // 4. Kullanıcı anahtar girince sessionStorage'a yaz ve soruyu bir kez otomatik tekrarla
  const handleSaveKeyAndRetry = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanKey = inputKey.trim();
    if (!cleanKey) return;

    // sessionStorage'a yaz (anahtar asla console.log veya localStorage'a yazılmaz)
    kysApi.setLlmSessionConfig(selectedProvider, cleanKey);
    setSessionLlm(kysApi.getLlmSessionConfig());
    setShowKeyModal(false);
    setInputKey('');

    // Soruyu bir kez otomatik tekrarla
    const qToRetry = pendingQuestion || question;
    if (qToRetry.trim()) {
      handleAsk(qToRetry, true);
    }
  };

  // 5. "Anahtarı unut" düğmesi: sessionStorage'ı temizler ve başlıklar bir daha gönderilmez
  const handleForgetKey = () => {
    kysApi.clearLlmSessionConfig();
    setSessionLlm(null);
  };

  const handleOpenManualKeyModal = () => {
    const current = kysApi.getLlmSessionConfig();
    if (current) {
      setSelectedProvider(current.provider);
    }
    setModalDetail('KYS asistanı için oturum boyunca geçerli olacak model sağlayıcısı ve API anahtarınızı belirleyebilirsiniz.');
    setInputKey('');
    setShowKeyModal(true);
  };

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={18} color="var(--accent)" />
            <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
              KYS Kaynaklı Soru Asistanı
            </h2>
          </div>
          {/* Model Ayarı kısayolu */}
          <button
            type="button"
            className="icon-btn"
            style={{ fontSize: '12px', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: 5 }}
            onClick={handleOpenManualKeyModal}
            title="Model ve API Anahtarı Ayarları"
          >
            <Settings2 size={13} />
            <span>Model Ayarı</span>
          </button>
        </div>

        {/* 5. Oturum anahtarı etkinse gösterilen bilgi çubuğu ve "Anahtarı unut" düğmesi */}
        {sessionLlm && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '7px 12px',
              backgroundColor: 'var(--panel-hover)',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--line)',
              fontSize: '12.5px',
              marginBottom: 14,
              flexWrap: 'wrap',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <KeyRound size={14} color="var(--accent)" />
              <span>
                Oturum Sağlayıcısı: <strong>{sessionLlm.provider === 'gemini' ? 'Google Gemini' : 'Anthropic Claude'}</strong> (Anahtar bu oturum için tanımlı)
              </span>
            </div>
            <button
              type="button"
              className="icon-btn"
              style={{
                fontSize: '12px',
                padding: '3px 8px',
                color: 'var(--danger)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
              }}
              onClick={handleForgetKey}
              title="Bu oturumdaki anahtarı sil ve sunucu varsayılanına dön"
            >
              <Trash2 size={12} />
              <span>Anahtarı Unut</span>
            </button>
          </div>
        )}

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
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <BookOpen size={18} color="var(--accent)" />
                <h3 style={{ margin: 0, fontSize: '16px' }}>Cevap</h3>

                {/* 6. Cevaptaki "model" alanını küçük bir etiketle göster */}
                {result.model && (
                  <span
                    className="badge badge-gray"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: '11.5px',
                      fontWeight: 600,
                    }}
                    title={`Kullanılan model: ${result.model}`}
                  >
                    <Cpu size={12} color="var(--accent)" />
                    {formatModelBadge(result.model)}
                  </span>
                )}
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

      {/* 2. & 3. Anahtar Kutusu Modalı (Yalnızca MODEL_YOK veya manuel açıldığında) */}
      {showKeyModal && (
        <div
          className="modal-backdrop"
          onClick={() => {
            setShowKeyModal(false);
            if (modalDetail && !error) {
              setError(modalDetail);
            }
          }}
        >
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <KeyRound size={20} color="var(--accent)" />
                <h2 className="modal-title">Model ve Sağlayıcı Tanımla</h2>
              </div>
              <button
                className="icon-btn"
                onClick={() => {
                  setShowKeyModal(false);
                  if (modalDetail && !error) {
                    setError(modalDetail);
                  }
                }}
                aria-label="Kapat"
                style={{ padding: '4px 8px' }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 16px 0' }}>
              {modalDetail || 'Sunucuda varsayılan model bulunamadı. Sorunun yanıtlanabilmesi için bir sağlayıcı ve API anahtarı giriniz.'}
            </p>

            <form onSubmit={handleSaveKeyAndRetry} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* 3. Sağlayıcı seçenekleri sadece "gemini" ve "anthropic" */}
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 600, fontSize: '13.5px' }}>
                  Model Sağlayıcısı
                </label>
                <div style={{ display: 'flex', gap: 12 }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: '13.5px',
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      border: `1px solid ${selectedProvider === 'gemini' ? 'var(--accent)' : 'var(--line)'}`,
                      backgroundColor: selectedProvider === 'gemini' ? 'var(--accent-soft)' : 'transparent',
                      flex: 1,
                    }}
                  >
                    <input
                      type="radio"
                      name="llm_provider"
                      value="gemini"
                      checked={selectedProvider === 'gemini'}
                      onChange={() => setSelectedProvider('gemini')}
                    />
                    <span>Google Gemini</span>
                  </label>

                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      fontSize: '13.5px',
                      cursor: 'pointer',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius)',
                      border: `1px solid ${selectedProvider === 'anthropic' ? 'var(--accent)' : 'var(--line)'}`,
                      backgroundColor: selectedProvider === 'anthropic' ? 'var(--accent-soft)' : 'transparent',
                      flex: 1,
                    }}
                  >
                    <input
                      type="radio"
                      name="llm_provider"
                      value="anthropic"
                      checked={selectedProvider === 'anthropic'}
                      onChange={() => setSelectedProvider('anthropic')}
                    />
                    <span>Anthropic Claude</span>
                  </label>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: 6, fontWeight: 600, fontSize: '13.5px' }}>
                  API Anahtarı ({selectedProvider === 'gemini' ? 'Gemini API Key' : 'Anthropic API Key'})
                </label>
                <input
                  type="password"
                  placeholder={selectedProvider === 'gemini' ? 'AIzaSy...' : 'sk-ant-...'}
                  value={inputKey}
                  onChange={(e) => setInputKey(e.target.value)}
                  autoComplete="off"
                  required
                />
                <small style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block', marginTop: 4 }}>
                  Güvenlik için anahtar yalnızca oturum süresince tarayıcı belleğinde (sessionStorage) saklanır ve X-LLM-* başlıklarıyla iletilir.
                </small>
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    setShowKeyModal(false);
                    if (modalDetail && !error) {
                      setError(modalDetail);
                    }
                  }}
                  style={{ flex: 1 }}
                >
                  Vazgeç
                </button>
                <button
                  type="submit"
                  className="primary"
                  disabled={!inputKey.trim()}
                  style={{ flex: 1 }}
                >
                  Kaydet ve Soruyu Yanıtla
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
