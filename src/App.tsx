import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { kysApi } from './services/apiClient';
import { StatsResponse, HealthResponse } from './types/kys';
import { Header } from './components/Header';
import { Nav, TabType } from './components/Nav';
import { AskTab } from './components/AskTab';
import { SearchTab } from './components/SearchTab';
import { DocsTab } from './components/DocsTab';
import { DocDetailTab } from './components/DocDetailTab';
import { ProcessesTab } from './components/ProcessesTab';
import { RefsTab } from './components/RefsTab';
import { SettingsModal } from './components/SettingsModal';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<TabType>('ask');
  const [activeDocCode, setActiveDocCode] = useState<string | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loadingStats, setLoadingStats] = useState<boolean>(false);
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Theme Management
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const saved = localStorage.getItem('kys_theme');
      if (saved === 'dark' || saved === 'light') return saved;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('kys_theme', theme);
    } catch {
      // ignore
    }
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const refreshData = useCallback(async () => {
    setLoadingStats(true);
    try {
      const [h, s] = await Promise.allSettled([
        kysApi.getHealth(),
        kysApi.getStats(),
      ]);

      if (h.status === 'fulfilled') {
        setHealth(h.value);
      } else {
        setHealth(null);
      }

      if (s.status === 'fulfilled') {
        setStats(s.value);
      } else {
        // If stats failed, it could be 401 or network
        setStats(null);
      }
    } catch (e) {
      console.error('Veriler yenilenirken hata:', e);
    } finally {
      setLoadingStats(false);
    }
  }, []);

  // Listen for 401 Unauthorized globally
  useEffect(() => {
    const unsubscribe = kysApi.onUnauthorized(() => {
      setShowSettings(true);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    refreshData();
  }, [refreshData]);

  const availableTypes = useMemo(() => {
    if (!stats || !stats.by_type) return [];
    return Object.keys(stats.by_type).sort();
  }, [stats]);

  const handleOpenDoc = (code: string) => {
    setActiveDocCode(code);
    setCurrentTab('doc');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCloseDoc = () => {
    setCurrentTab('docs');
  };

  return (
    <>
      <Header
        stats={stats}
        health={health}
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenSettings={() => setShowSettings(true)}
        onRefresh={refreshData}
        loading={loadingStats}
      />

      <main>
        <Nav
          currentTab={currentTab}
          onSelectTab={setCurrentTab}
          activeDocCode={activeDocCode}
        />

        {currentTab === 'ask' && (
          <AskTab onOpenDoc={handleOpenDoc} />
        )}

        {currentTab === 'search' && (
          <SearchTab onOpenDoc={handleOpenDoc} />
        )}

        {currentTab === 'docs' && (
          <DocsTab
            onOpenDoc={handleOpenDoc}
            availableTypes={availableTypes}
          />
        )}

        {currentTab === 'processes' && (
          <ProcessesTab onOpenDoc={handleOpenDoc} />
        )}

        {currentTab === 'refs' && (
          <RefsTab onOpenDoc={handleOpenDoc} />
        )}

        {currentTab === 'doc' && activeDocCode && (
          <DocDetailTab
            code={activeDocCode}
            onOpenDoc={handleOpenDoc}
            onClose={handleCloseDoc}
          />
        )}
      </main>

      {showSettings && (
        <SettingsModal
          onClose={() => setShowSettings(false)}
          onSaved={refreshData}
        />
      )}
    </>
  );
};

export default App;
