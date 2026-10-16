import React, { useMemo } from 'react';
import { kysStore } from '../services/kysStore';

interface RefsTabProps {
  onOpenDoc: (code: string) => void;
  hasDocuments: boolean;
}

export const RefsTab: React.FC<RefsTabProps> = ({ onOpenDoc, hasDocuments }) => {
  const references = useMemo(() => {
    return kysStore.getReferences();
  }, [hasDocuments]);

  if (!hasDocuments) {
    return (
      <section id="tab-refs">
        <div className="card meta">
          Sistemde onaylı doküman bulunmadığı için atıf analizi mevcut değildir.
        </div>
      </section>
    );
  }

  return (
    <section id="tab-refs">
      <div id="refs-out">
        <div className="card">
          <div className="meta" style={{ marginBottom: '10px' }}>
            Dokümanlarda atıf yapılan ama sistemde bulunmayan kodlar
          </div>
          <table>
            <thead>
              <tr>
                <th style={{ width: '150px' }}>Eksik Doküman Kodu</th>
                <th>Atıf Yapan Kaynaklar</th>
              </tr>
            </thead>
            <tbody>
              {references.missing_documents.length > 0 ? (
                references.missing_documents.map((m) => (
                  <tr key={m.code}>
                    <td>
                      <b style={{ color: 'var(--warn)' }}>{m.code}</b>
                    </td>
                    <td className="meta">
                      {m.referenced_from.map((c, idx) => (
                        <React.Fragment key={c}>
                          {idx > 0 && ', '}
                          <span
                            className="ref"
                            onClick={() => onOpenDoc(c)}
                          >
                            {c}
                          </span>
                        </React.Fragment>
                      ))}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={2} className="meta">
                    Eksik doküman atfı bulunamadı.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card meta">
          Doküman kodu olmayabilir (makine/hat adı):{' '}
          {references.probably_not_documents.length > 0
            ? references.probably_not_documents.join(', ')
            : '-'}
        </div>
      </div>
    </section>
  );
};
