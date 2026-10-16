import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { kysStore } from './services/kysStore';
import { StatsResponse } from './types/kys';
import { Header } from './components/Header';
import { Nav, TabType } from './components/Nav';
import { AskTab } from './components/AskTab';
import { SearchTab } from './components/SearchTab';
import { DocsTab } from './components/DocsTab';
import { RefsTab } from './components/RefsTab';
import { DocDetailTab } from './components/DocDetailTab';
import { LoginModal } from './components/LoginModal';
import { DriveModal } from './components/DriveModal';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<TabType>('ask');
  const [activeDocCode, setActiveDocCode] = useState<string | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [token, setToken] = useState<string>('');
  const [showLogin, setShowLogin] = useState<boolean>(false);
  const [showDrive, setShowDrive] = useState<boolean>(false);

  const refreshData = useCallback(() => {
    try {
      const s = kysStore.getStats();
      setStats(s);
    } catch (e) {
      console.error('Failed to load stats', e);
    }
  }, []);

  useEffect(() => {
    // Load local API token from localStorage
    try {
      const savedToken = localStorage.getItem('kys-token') || '';
      setToken(savedToken);
    } catch {
      // ignore
    }

    refreshData();
  }, [refreshData]);

  const availableTypes = useMemo(() => {
    if (!stats || !stats.by_type) return [];
    return Object.keys(stats.by_type).sort();
  }, [stats]);

  const hasDocuments = Boolean(stats && stats.documents > 0);

  const handleOpenDoc = (code: string) => {
    setActiveDocCode(code);
    setCurrentTab('doc');
  };

  const handleCloseDoc = () => {
    setCurrentTab('docs');
  };

  const handleSaveToken = (newToken: string) => {
    setToken(newToken);
    try {
      if (newToken) {
        localStorage.setItem('kys-token', newToken);
      } else {
        localStorage.removeItem('kys-token');
      }
    } catch {
      // ignore
    }
  };

  return (
    <>
      <Header
        stats={stats}
        hasToken={Boolean(token)}
        onOpenLogin={() => setShowLogin(true)}
        onOpenDrive={() => setShowDrive(true)}
      />

      <main>
        <Nav
          currentTab={currentTab}
          onSelectTab={setCurrentTab}
          activeDocCode={activeDocCode}
        />

        {currentTab === 'ask' && (
          <AskTab onOpenDoc={handleOpenDoc} hasDocuments={hasDocuments} />
        )}
        {currentTab === 'search' && (
          <SearchTab onOpenDoc={handleOpenDoc} hasDocuments={hasDocuments} />
        )}
        {currentTab === 'docs' && (
          <DocsTab
            onOpenDoc={handleOpenDoc}
            availableTypes={availableTypes}
            onDataChanged={refreshData}
            onOpenDrive={() => setShowDrive(true)}
          />
        )}
        {currentTab === 'refs' && (
          <RefsTab onOpenDoc={handleOpenDoc} hasDocuments={hasDocuments} />
        )}
        {currentTab === 'doc' && activeDocCode && (
          <DocDetailTab
            code={activeDocCode}
            onOpenDoc={handleOpenDoc}
            onClose={handleCloseDoc}
          />
        )}
      </main>

      {showLogin && (
        <LoginModal
          initialToken={token}
          onSaveToken={handleSaveToken}
          onClose={() => setShowLogin(false)}
        />
      )}

      {showDrive && (
        <DriveModal
          onClose={() => setShowDrive(false)}
          onDataImported={refreshData}
        />
      )}
    </>
  );
};

export default App;
