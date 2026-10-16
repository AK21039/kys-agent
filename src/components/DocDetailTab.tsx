import React, { useMemo } from 'react';
import { kysStore } from '../services/kysStore';

interface DocDetailTabProps {
  code: string;
  onOpenDoc: (code: string) => void;
  onClose: () => void;
}

export const DocDetailTab: React.FC<DocDetailTabProps> = ({ code, onOpenDoc, onClose }) => {
  const doc = useMemo(() => {
    return kysStore.getDocument(code);
  }, [code]);

  if (!doc) {
    return (
      <section id="tab-doc">
        <div className="card">
          <div className="warn">Doküman bulunamadı: {code}</div>
          <button
            type="button"
            className="header-btn"
            style={{ marginTop: '10px' }}
            onClick={onClose}
          >
            ← Geri Dön
          </button>
        </div>
      </section>
    );
  }

  return (
    <section id="tab-doc">
      <div id="doc-out">
        <div className="card">
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
            title="Kapat"
          >
            ✕
          </button>
          <div>
            <span className="pill">{doc.doc_type}</span>
            <b>
              {doc.code} Rev.{doc.revision}
            </b>{' '}
            — {doc.title}
          </div>
          <div className="meta" style={{ marginTop: '4px' }}>
            {doc.status}
            {doc.revision_date ? ` · Rev. tarihi ${doc.revision_date}` : ''}
            {doc.effective_date ? ` · Yürürlük ${doc.effective_date}` : ''}
            {doc.owner_unit ? ` · ${doc.owner_unit}` : ''}
          </div>
          {doc.summary && <p style={{ margin: '8px 0 4px' }}>{doc.summary}</p>}
          {doc.warnings && doc.warnings.length > 0 && (
            <div style={{ marginTop: '6px' }}>
              {doc.warnings.map((w, idx) => (
                <div key={idx} className="warn" style={{ marginTop: '4px' }}>
                  {w}
                </div>
              ))}
            </div>
          )}
        </div>

        {doc.references && doc.references.length > 0 && (
          <div className="card meta">
            Atıf yaptığı:{' '}
            {doc.references.map((r, idx) => (
              <React.Fragment key={idx}>
                {idx > 0 && ', '}
                {r.target_code ? (
                  <span
                    className="ref"
                    onClick={() => onOpenDoc(r.target_code!)}
                    title={r.target_title || undefined}
                  >
                    {r.ref_code}
                  </span>
                ) : (
                  <span>{r.ref_code} (sistemde yok)</span>
                )}
              </React.Fragment>
            ))}
          </div>
        )}

        {doc.referenced_by && doc.referenced_by.length > 0 && (
          <div className="card meta">
            Atıf yapan:{' '}
            {doc.referenced_by.map((r, idx) => (
              <React.Fragment key={idx}>
                {idx > 0 && ', '}
                <span
                  className="ref"
                  onClick={() => onOpenDoc(r.code)}
                  title={r.title}
                >
                  {r.code}
                </span>
              </React.Fragment>
            ))}
          </div>
        )}

        {doc.sections.map((s) => (
          <div key={s.id} className="card">
            <b>{s.heading_path || s.heading || ''}</b>
            <pre>{s.text}</pre>
          </div>
        ))}
      </div>
    </section>
  );
};
