import React, { useState } from 'react';
import { kysApi } from '../services/apiClient';
import { HealthResponse } from '../types/kys';
import { X, CheckCircle, AlertCircle, RefreshCw, KeyRound, Server } from 'lucide-react';

interface SettingsModalProps {
  onClose: () => void;
  onSaved: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose, onSaved }) => {
  const currentConfig = kysApi.getApiConfig();
  const [apiBase, setApiBase] = useState<string>(currentConfig.savedApiBase || '');
  const [token, setToken] = useState<string>(currentConfig.token);
  const [testing, setTesting] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    data?: HealthResponse;
    error?: string;
  } | null>(null);

  const activeBase = apiBase.trim() || currentConfig.apiBase;

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      // Temporarily store to test with current input
      kysApi.setApiConfig(apiBase, token);
      const health = await kysApi.getHealth();
      setTestResult({
        success: true,
        data: health,
      });
    } catch (err: unknown) {
      setTestResult({
        success: false,
        error: err instanceof Error ? err.message : 'Bağlantı hatası',
      });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    kysApi.setApiConfig(apiBase, token);
    onSaved();
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Server size={20} color="var(--accent)" />
            <h2 className="modal-title">API & Bağlantı Ayarları</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Kapat" style={{ padding: '4px 8px' }}>
            <X size={18} />
          </button>
        </div>

        <p style={{ color: 'var(--text-muted)', fontSize: '13px', margin: '0 0 16px 0' }}>
          KYS REST API servisine bağlanmak için sunucu adresini ve erişim token'ınızı girin. Bilgiler yalnızca yerel tarayıcınızda (localStorage) saklanır.
        </p>

        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600, fontSize: '13.5px' }}>
              API Base URL
            </label>
            <input
              type="text"
              placeholder={currentConfig.apiBase ? `Otomatik: ${currentConfig.apiBase}` : 'Örn: https://kys-servisi.sirket.com veya /qa'}
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              autoComplete="off"
            />
            <small style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block', marginTop: 4 }}>
              Tüm istekler bu taban adrese yapılır (ör. <code>{activeBase ? `${activeBase.replace(/\/+$/, '')}/api/health` : '/api/health'}</code>).
            </small>
          </div>

          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600, fontSize: '13.5px' }}>
              Erişim Token'ı (Bearer Token)
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="password"
                placeholder="Örn: eyJhbGciOi..."
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            <small style={{ color: 'var(--text-muted)', fontSize: '12px', display: 'block', marginTop: 4 }}>
              /api/health dışındaki tüm API isteklerinde <code>Authorization: Bearer &lt;token&gt;</code> başlığı olarak gönderilir.
            </small>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
            <button
              type="button"
              className="secondary"
              onClick={handleTest}
              disabled={testing}
              style={{ flex: 1 }}
            >
              {testing ? <RefreshCw size={16} className="spin" /> : <KeyRound size={16} />}
              Bağlantıyı Sına
            </button>
            <button type="submit" className="primary" style={{ flex: 1 }}>
              Kaydet ve Kapat
            </button>
          </div>
        </form>

        {testResult && (
          <div
            style={{
              marginTop: 16,
              padding: '12px 14px',
              borderRadius: 'var(--radius)',
              backgroundColor: testResult.success ? 'var(--ok-soft)' : 'var(--danger-soft)',
              border: `1px solid ${testResult.success ? 'var(--ok-border)' : 'var(--danger-border)'}`,
              color: testResult.success ? 'var(--ok)' : 'var(--danger)',
              fontSize: '13.5px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
              {testResult.success ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
              {testResult.success ? 'Bağlantı Başarılı!' : 'Bağlantı Başarısız!'}
            </div>
            {testResult.data && (
              <div style={{ marginTop: 6, fontSize: '12.5px', color: 'var(--text)' }}>
                Durum: <strong>{testResult.data.ok ? 'Aktif' : 'Pasif'}</strong> | Kimlik Doğrulama: <strong>{testResult.data.auth ? 'Gerekli' : 'Gereksiz'}</strong> | Model: <strong>{testResult.data.model || 'Bilinmiyor'}</strong>
              </div>
            )}
            {testResult.error && (
              <div style={{ marginTop: 4, fontSize: '12.5px' }}>
                Hata: {testResult.error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
