import React, { useState, useMemo } from 'react';
import { kysStore } from '../services/kysStore';

interface DocsTabProps {
  onOpenDoc: (code: string) => void;
  availableTypes: string[];
  onDataChanged: () => void;
  onOpenDrive: () => void;
}

export const DocsTab: React.FC<DocsTabProps> = ({
  onOpenDoc,
  availableTypes,
  onDataChanged,
  onOpenDrive,
}) => {
  const [docType, setDocType] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const documents = useMemo(() => {
    return kysStore.getDocuments(docType);
  }, [docType, availableTypes]);

  const handleImport = (e: React.FormEvent) => {
    e.preventDefault();
    if (!jsonInput.trim()) return;
    try {
      const parsed = JSON.parse(jsonInput.trim());
      const res = kysStore.importDatabase(parsed);
      if (res.success) {
        setImportStatus(`${res.count} adet onaylı doküman başarıyla yüklendi.`);
        setJsonInput('');
        setShowImport(false);
        onDataChanged();
      } else {
        setImportStatus(`Hata: ${res.error}`);
      }
    } catch (err: any) {
      setImportStatus(`JSON parse hatası: ${err.message}`);
    }
  };

  const handleClear = () => {
    if (window.confirm('Kayıtlı tüm dokümanlar silinecektir. Onaylıyor musunuz?')) {
      kysStore.clearDatabase();
      onDataChanged();
    }
  };

  return (
    <section id="tab-docs">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', gap: '8px', flexWrap: 'wrap' }}>
        <form id="docs-form" onSubmit={(e) => e.preventDefault()} style={{ margin: 0, flex: 1 }}>
          <select
            id="doctype"
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            disabled={availableTypes.length === 0}
          >
            <option value="">Tüm tipler {availableTypes.length > 0 ? `(${documents.length})` : ''}</option>
            {availableTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </form>

        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="header-btn"
            style={{ borderColor: 'var(--accent)', color: 'var(--accent)', fontWeight: 500 }}
            onClick={onOpenDrive}
          >
            📁 Google Drive'dan Aktar
          </button>
          <button
            type="button"
            className="header-btn"
            onClick={() => setShowImport(!showImport)}
          >
            {showImport ? 'İptal' : '📥 JSON Yükle'}
          </button>
          {documents.length > 0 && (
            <button
              type="button"
              className="header-btn"
              style={{ color: 'var(--warn)' }}
              onClick={handleClear}
            >
              Verileri Temizle
            </button>
          )}
        </div>
      </div>

      {importStatus && (
        <div className="card warn" style={{ marginBottom: '10px' }}>
          {importStatus}
        </div>
      )}

      {showImport && (
        <div className="card" style={{ marginBottom: '14px' }}>
          <b style={{ display: 'block', marginBottom: '6px' }}>Onaylı KYS Doküman Verisi Yükle</b>
          <div className="meta" style={{ marginBottom: '8px' }}>
            Yalnızca onayladığınız dokümanları içeren JSON dizisini yapıştırın. Sistem kaynağı belirsiz hiçbir veriyi otomatik eklemez.
          </div>
          <form onSubmit={handleImport} style={{ flexDirection: 'column' }}>
            <textarea
              style={{ minHeight: '120px', fontFamily: 'monospace', fontSize: '13px' }}
              placeholder='[{"code": "PR-01", "revision": "01", "title": "...", "doc_type": "PROSEDUR", "status": "YURURLUKTE", "sections": [{"clause_no": "1.0", "heading": "...", "text": "..."}]}]'
              value={jsonInput}
              onChange={(e) => setJsonInput(e.target.value)}
            />
            <button type="submit" disabled={!jsonInput.trim()}>
              Dokümanları Yükle ve Onayla
            </button>
          </form>
        </div>
      )}

      <div id="docs-out">
        {documents.length > 0 ? (
          <div className="card">
            <table>
              <thead>
                <tr>
                  <th style={{ width: '130px' }}>Kod</th>
                  <th>Doküman</th>
                  <th className="hide-sm" style={{ width: '150px' }}>Tip</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.code}>
                    <td>
                      <span
                        className="ref"
                        onClick={() => onOpenDoc(d.code)}
                      >
                        {d.code} Rev.{d.revision}
                      </span>
                    </td>
                    <td>
                      <span
                        style={{ cursor: 'pointer', fontWeight: 500 }}
                        onClick={() => onOpenDoc(d.code)}
                      >
                        {d.title}
                      </span>
                      {d.owner_unit && (
                        <div className="meta" style={{ fontSize: '12px' }}>
                          {d.owner_unit}
                        </div>
                      )}
                    </td>
                    <td className="hide-sm meta">{d.doc_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="card">
            <div className="meta" style={{ textAlign: 'center', padding: '24px 12px' }}>
              Henüz onaylanmış veya sisteme aktarılmış bir doküman bulunmuyor.
              <br />
              <small style={{ display: 'block', marginTop: '6px', color: 'var(--muted)' }}>
                Google Drive üzerindeki "KYS Agent &gt; docs" klasörünüzden veya JSON formatında onaylı dosyalarınızı aktarabilirsiniz.
              </small>
              <div style={{ marginTop: '12px' }}>
                <button
                  type="button"
                  className="header-btn"
                  style={{ borderColor: 'var(--accent)', color: 'var(--accent)', fontWeight: 600, padding: '6px 14px' }}
                  onClick={onOpenDrive}
                >
                  📁 Google Drive'a Bağlan ("KYS Agent &gt; docs")
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
