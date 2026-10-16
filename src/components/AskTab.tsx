import React, { useState } from 'react';
import { AskResponse } from '../types/kys';
import { kysStore } from '../services/kysStore';

interface AskTabProps {
  onOpenDoc: (code: string) => void;
  hasDocuments: boolean;
}

export const AskTab: React.FC<AskTabProps> = ({ onOpenDoc, hasDocuments }) => {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = question.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
    try {
      const resp = await kysStore.askQuestion(q);
      setResult(resp);
    } catch (err: any) {
      setError(err?.message || 'Bir hata oluştu');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="tab-ask">
      <form onSubmit={handleSubmit}>
        <textarea
          id="question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Soru girin..."
          disabled={!hasDocuments}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              handleSubmit();
            }
          }}
        />
        <button type="submit" disabled={loading || !question.trim() || !hasDocuments}>
          {loading ? 'Soruluyor…' : 'Sor'}
        </button>
      </form>

      {!hasDocuments && (
        <div className="card warn">
          Henüz onaylanmış veya yüklenmiş bir doküman veritabanı bulunmuyor.
          <div className="meta" style={{ marginTop: '4px' }}>
            Sorgu yapılabilmesi için sisteme onaylı KYS dokümanlarının yüklenmesi gerekmektedir.
          </div>
        </div>
      )}

      <div id="ask-out">
        {loading && <div className="meta">Dokümanlar taranıyor…</div>}

        {error && <div className="warn">{error}</div>}

        {result && (
          <>
            <div className="card">
              <div className="answer">{result.answer}</div>
              {!result.yeterli_bilgi && (
                <div className="warn" style={{ marginTop: '8px' }}>
                  Dokümanlar bu soruyu tam cevaplamaya yetmiyor.
                </div>
              )}
              {result.unverified > 0 && (
                <div className="warn" style={{ marginTop: '8px' }}>
                  {result.unverified} alıntı kaynak metinde doğrulanamadığı için gösterilmedi.
                </div>
              )}
              <div className="meta" style={{ marginTop: '8px' }}>
                {result.model}
              </div>
            </div>

            {result.citations.map((c, i) => (
              <div key={i} className="card">
                [{c.no}]{' '}
                <span
                  className="ref"
                  onClick={() => onOpenDoc(c.code)}
                  title="Dokümanı görüntüle"
                >
                  {c.code} Rev.{c.revision}
                  {c.clause_no ? ` md.${c.clause_no}` : ''}
                </span>{' '}
                <span className="meta">{c.title}</span>
                <div className="quote">{c.quote}</div>
              </div>
            ))}
          </>
        )}
      </div>
    </section>
  );
};
