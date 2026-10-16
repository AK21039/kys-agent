import React, { useState } from 'react';

interface LoginModalProps {
  initialToken: string;
  onSaveToken: (token: string) => void;
  onClose: () => void;
}

export const LoginModal: React.FC<LoginModalProps> = ({
  initialToken,
  onSaveToken,
  onClose,
}) => {
  const [tokenInput, setTokenInput] = useState(initialToken);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSaveToken(tokenInput.trim());
    onClose();
  };

  const handleClear = () => {
    setTokenInput('');
    onSaveToken('');
    onClose();
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '440px',
          margin: 0,
          boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <h2 style={{ fontSize: '16px', margin: 0 }}>API Erişim Anahtarı</h2>
          <button
            type="button"
            className="close-btn"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <form onSubmit={handleSubmit} style={{ marginBottom: '8px' }}>
          <input
            id="token"
            type="password"
            placeholder="Erişim anahtarı"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            autoComplete="current-password"
            autoFocus
          />
          <button type="submit">Kaydet</button>
        </form>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div className="meta">Anahtar yalnızca bu tarayıcıda saklanır.</div>
          {initialToken && (
            <button
              type="button"
              className="header-btn"
              onClick={handleClear}
              style={{ color: 'var(--warn)' }}
            >
              Anahtarı Temizle
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
