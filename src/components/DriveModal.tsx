import React, { useState, useEffect } from 'react';
import { User } from 'firebase/auth';
import { googleSignIn, logout, initAuth } from '../services/firebaseAuth';
import { GoogleDriveService, DriveFolder, DriveFile } from '../services/googleDriveService';
import { kysStore } from '../services/kysStore';
import { DocumentItem } from '../types/kys';

interface DriveModalProps {
  onClose: () => void;
  onDataImported: () => void;
}

export const DriveModal: React.FC<DriveModalProps> = ({ onClose, onDataImported }) => {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [folders, setFolders] = useState<DriveFolder[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string>('');
  const [files, setFiles] = useState<DriveFile[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    const unsubscribe = initAuth(
      (currentUser, accessToken) => {
        setUser(currentUser);
        setToken(accessToken);
        findFolders(accessToken);
      },
      () => {
        setUser(null);
        setToken(null);
      }
    );
    return () => unsubscribe();
  }, []);

  const handleLogin = async () => {
    setIsLoggingIn(true);
    setErrorMessage('');
    try {
      const res = await googleSignIn();
      if (res) {
        setUser(res.user);
        setToken(res.accessToken);
        await findFolders(res.accessToken);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Google Drive bağlantısı kurulamadı.');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    setUser(null);
    setToken(null);
    setFolders([]);
    setFiles([]);
    setSelectedFolderId('');
    setSelectedFileIds(new Set());
  };

  const findFolders = async (accessToken: string) => {
    setLoading(true);
    setStatusMessage('Google Drive üzerinde "KYS Agent > docs" klasörü aranıyor...');
    setErrorMessage('');
    try {
      const found = await GoogleDriveService.findKysFolders(accessToken);
      setFolders(found);
      if (found.length > 0) {
        // En uygun klasörü seç (tercihen 'KYS Agent > docs' veya 'docs')
        const best = found.find((f) => f.path.toLowerCase().includes('docs')) || found[0];
        setSelectedFolderId(best.id);
        await loadFiles(accessToken, best.id);
      } else {
        setStatusMessage('Google Drive üzerinde "KYS Agent" veya "docs" klasörü bulunamadı. Lütfen klasör adını kontrol edin.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Klasörler taranırken bir hata oluştu.');
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async (accessToken: string, folderId: string) => {
    setLoading(true);
    setStatusMessage('Klasördeki dokümanlar listeleniyor...');
    setErrorMessage('');
    try {
      const list = await GoogleDriveService.listFilesInFolder(accessToken, folderId);
      setFiles(list);
      // Varsayılan olarak tüm desteklenen dosyaları seç
      const validIds = new Set(list.map((f) => f.id));
      setSelectedFileIds(validIds);
      setStatusMessage(`${list.length} adet dosya bulundu.`);
    } catch (err: any) {
      setErrorMessage(err.message || 'Dosyalar listelenemedi.');
    } finally {
      setLoading(false);
    }
  };

  const handleFolderChange = async (folderId: string) => {
    setSelectedFolderId(folderId);
    if (token) {
      await loadFiles(token, folderId);
    }
  };

  const toggleSelectFile = (fileId: string) => {
    const updated = new Set(selectedFileIds);
    if (updated.has(fileId)) {
      updated.delete(fileId);
    } else {
      updated.add(fileId);
    }
    setSelectedFileIds(updated);
  };

  const handleSelectAll = () => {
    if (selectedFileIds.size === files.length) {
      setSelectedFileIds(new Set());
    } else {
      setSelectedFileIds(new Set(files.map((f) => f.id)));
    }
  };

  const handleImportSelected = async () => {
    if (!token || selectedFileIds.size === 0) return;
    setLoading(true);
    setErrorMessage('');
    setStatusMessage('Seçili dokümanlar Drive üzerinden okunuyor ve işleniyor...');

    const importedDocs: DocumentItem[] = [];

    try {
      const selectedFiles = files.filter((f) => selectedFileIds.has(f.id));

      for (const file of selectedFiles) {
        setStatusMessage(`Okunuyor: ${file.name}...`);
        const content = await GoogleDriveService.readFileContent(token, file);
        const parsedList = GoogleDriveService.parseFileToDocuments(file.name, content);
        importedDocs.push(...parsedList);
      }

      if (importedDocs.length === 0) {
        throw new Error('Dosyalardan geçerli doküman içeriği çıkarılamadı.');
      }

      // Dokümanları KysStore'a aktar ve onayla
      const res = kysStore.importDatabase(importedDocs);
      if (res.success) {
        setStatusMessage(`Başarılı: ${res.count} adet doküman onaylandı ve KYS bilgi tabanına aktarıldı!`);
        onDataImported();
        setTimeout(() => {
          onClose();
        }, 1200);
      } else {
        setErrorMessage(res.error || 'İçe aktarım başarısız oldu.');
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Dokümanlar içe aktarılırken hata oluştu.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
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
          maxWidth: '560px',
          maxHeight: '90vh',
          overflowY: 'auto',
          margin: 0,
          boxShadow: '0 8px 30px rgba(0,0,0,0.2)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <div>
            <b style={{ fontSize: '16px' }}>Google Drive'dan Doküman Aktar</b>
            <div className="meta">KYS Agent &gt; docs klasörünüzdeki resmi dokümanlar</div>
          </div>
          <button type="button" className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {errorMessage && (
          <div className="card warn" style={{ marginBottom: '10px' }}>
            {errorMessage}
          </div>
        )}

        {!user ? (
          <div style={{ padding: '24px 12px', textAlign: 'center' }}>
            <p className="meta" style={{ marginBottom: '16px' }}>
              Google Drive üzerindeki "KYS Agent &gt; docs" klasörünüzde bulunan dokümanları okumak için Google hesabınızla giriş yapın.
            </p>
            <button
              type="button"
              className="gsi-material-button"
              onClick={handleLogin}
              disabled={isLoggingIn}
            >
              <div className="gsi-material-button-state"></div>
              <div className="gsi-material-button-content-wrapper">
                <div className="gsi-material-button-icon">
                  <svg
                    version="1.1"
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 48 48"
                    xmlnsXlink="http://www.w3.org/1999/xlink"
                    style={{ display: 'block' }}
                  >
                    <path
                      fill="#EA4335"
                      d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                    ></path>
                    <path
                      fill="#4285F4"
                      d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                    ></path>
                    <path
                      fill="#FBBC05"
                      d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                    ></path>
                    <path
                      fill="#34A853"
                      d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
                    ></path>
                    <path fill="none" d="M0 0h48v48H0z"></path>
                  </svg>
                </div>
                <span className="gsi-material-button-contents">Sign in with Google</span>
              </div>
            </button>
          </div>
        ) : (
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 12px',
                background: 'var(--accent-soft)',
                borderRadius: '6px',
                marginBottom: '14px',
              }}
            >
              <div>
                <span style={{ fontWeight: 600, fontSize: '13px' }}>{user.displayName || user.email}</span>
                <div className="meta" style={{ fontSize: '12px' }}>{user.email}</div>
              </div>
              <button
                type="button"
                className="header-btn"
                onClick={handleLogout}
              >
                Çıkış Yap
              </button>
            </div>

            {folders.length > 0 && (
              <div style={{ marginBottom: '12px' }}>
                <label className="meta" style={{ display: 'block', marginBottom: '4px' }}>
                  Hedef Klasör:
                </label>
                <select
                  value={selectedFolderId}
                  onChange={(e) => handleFolderChange(e.target.value)}
                  disabled={loading}
                >
                  {folders.map((f) => (
                    <option key={f.id} value={f.id}>
                      📁 {f.path}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {statusMessage && (
              <div className="meta" style={{ marginBottom: '10px' }}>
                {statusMessage}
              </div>
            )}

            {files.length > 0 && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className="meta">
                    Bulunan Dosyalar ({selectedFileIds.size}/{files.length} seçildi):
                  </span>
                  <button
                    type="button"
                    className="header-btn"
                    style={{ fontSize: '11px' }}
                    onClick={handleSelectAll}
                  >
                    {selectedFileIds.size === files.length ? 'Seçimi Kaldır' : 'Tümünü Seç'}
                  </button>
                </div>

                <div
                  style={{
                    maxHeight: '200px',
                    overflowY: 'auto',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    padding: '6px',
                    marginBottom: '14px',
                  }}
                >
                  {files.map((f) => (
                    <label
                      key={f.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        padding: '6px 8px',
                        borderBottom: '1px solid var(--line)',
                        cursor: 'pointer',
                        fontSize: '13px',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedFileIds.has(f.id)}
                        onChange={() => toggleSelectFile(f.id)}
                      />
                      <span style={{ flex: 1, wordBreak: 'break-all' }}>{f.name}</span>
                    </label>
                  ))}
                </div>

                <button
                  type="button"
                  style={{ width: '100%', padding: '10px' }}
                  disabled={loading || selectedFileIds.size === 0}
                  onClick={handleImportSelected}
                >
                  {loading ? 'İşleniyor…' : `Seçili (${selectedFileIds.size}) Dokümanı Aktar ve Onayla`}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
