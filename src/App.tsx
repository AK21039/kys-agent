import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { kysApi } from './services/apiClient';
import {
  StatsResponse,
  HealthResponse,
  DocumentSummary,
  FindingItem,
  ReferencesResponse,
  DecisionItem,
} from './types/kys';
import { KysSidebar } from './components/KysSidebar';
import { KysHeader } from './components/KysHeader';
import { KysDocGrid } from './components/KysDocGrid';
import { KysDocDetail } from './components/KysDocDetail';
import { KysAuditMatrix } from './components/KysAuditMatrix';
import { KysDecisionsTab } from './components/KysDecisionsTab';
import { KysToolModal } from './components/KysToolModal';
import { SettingsModal } from './components/SettingsModal';

export const App: React.FC = () => {
  // Navigation State
  const [activeTreeKey, setActiveTreeKey] = useState<string>('ALL');
  const [activeDocCode, setActiveDocCode] = useState<string | null>(null);
  const [docDetailInitialTab, setDocDetailInitialTab] = useState<'content' | 'conflicts' | 'gaps'>('content');
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Modals
  const [activeToolModal, setActiveToolModal] = useState<'ask' | 'search' | null>(null);
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Data State
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [missingRefs, setMissingRefs] = useState<ReferencesResponse | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(true);
  const [dataError, setDataError] = useState<string | null>(null);
  const [runningAudit, setRunningAudit] = useState<boolean>(false);

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

  // Main Data Fetcher
  const refreshData = useCallback(async () => {
    setLoadingData(true);
    setDataError(null);
    try {
      const [h, s, docs, fnds, refs, decs] = await Promise.allSettled([
        kysApi.getHealth(),
        kysApi.getStats(),
        kysApi.getDocuments(),
        kysApi.getFindings({ limit: 300 }),
        kysApi.getReferences().catch(() => null),
        kysApi.getDecisions().catch(() => [] as DecisionItem[]),
      ]);

      if (h.status === 'fulfilled') setHealth(h.value);
      if (s.status === 'fulfilled') setStats(s.value);
      if (docs.status === 'fulfilled') setDocuments(docs.value);
      if (fnds.status === 'fulfilled') setFindings(fnds.value);
      if (refs.status === 'fulfilled') setMissingRefs(refs.value);
      if (decs.status === 'fulfilled') setDecisions(decs.value);
    } catch (err: unknown) {
      setDataError(err instanceof Error ? err.message : 'Veriler güncellenirken hata oluştu');
    } finally {
      setLoadingData(false);
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

  // Run Global Audit Analysis
  const handleRunAudit = async () => {
    setRunningAudit(true);
    try {
      const res = await kysApi.runAuditAnalysis();
      await refreshData();
      alert(`Denetim ve Çakışma Analizi tamamlandı: ${res.findings_count} bulgu (${res.critical_count} kritik) güncellendi.`);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Denetim analizi çalıştırılamadı');
    } finally {
      setRunningAudit(false);
    }
  };

  // Computed Counts
  const conflictCount = useMemo(() => {
    return findings.filter(
      (f) =>
        f.status === 'ACIK' &&
        (f.finding_type === 'CAKISMA' || f.finding_type === 'YETKI_ASIMI' || f.finding_type === 'BELIRSIZLIK')
    ).length;
  }, [findings]);

  const gapCount = useMemo(() => {
    return findings.filter(
      (f) =>
        f.status === 'ACIK' &&
        (f.finding_type === 'BOSLUK' ||
          f.finding_type === 'EKSIK_ONAY' ||
          f.finding_type === 'GUNCELLIK' ||
          f.finding_type === 'UYGUNSUZLUK')
    ).length;
  }, [findings]);

  const missingRefsCount = useMemo(() => {
    return missingRefs?.missing_documents?.length || 0;
  }, [missingRefs]);

  const decisionCount = useMemo(() => {
    return decisions.length;
  }, [decisions]);

  const docCountsByType = useMemo(() => {
    const counts: Record<string, number> = {};
    documents.forEach((d) => {
      const t = d.doc_type || 'DIGER';
      counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
  }, [documents]);

  // Navigation Handlers
  const handleSelectTreeKey = (key: string) => {
    setActiveTreeKey(key);
    setActiveDocCode(null);
  };

  const handleOpenDoc = (code: string, tab: 'content' | 'conflicts' | 'gaps' = 'content') => {
    setActiveDocCode(code);
    setDocDetailInitialTab(tab);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleCloseDoc = () => {
    setActiveDocCode(null);
  };

  // Breadcrumbs builder
  const breadcrumbs = useMemo(() => {
    const crumbs: { label: string; onClick?: () => void }[] = [
      {
        label: 'KYS Doküman ve Denetim Merkezi',
        onClick: () => {
          setActiveTreeKey('ALL');
          setActiveDocCode(null);
        },
      },
    ];

    if (activeTreeKey === 'DECISIONS') {
      crumbs.push({ label: 'Karar Envanteri & Yetki Limitleri' });
    } else if (activeTreeKey === 'CONFLICTS') {
      crumbs.push({ label: 'Denetim Radarı' });
      crumbs.push({ label: 'Kural Çelişkileri (Çakışmalar)' });
    } else if (activeTreeKey === 'GAPS') {
      crumbs.push({ label: 'Denetim Radarı' });
      crumbs.push({ label: 'Açık Noktalar & Boşluklar' });
    } else if (activeTreeKey === 'MISSING_REFS') {
      crumbs.push({ label: 'Denetim Radarı' });
      crumbs.push({ label: 'Eksik / İptal Atıflar' });
    } else {
      crumbs.push({
        label: 'Doküman Yönetimi',
        onClick: activeDocCode ? () => setActiveDocCode(null) : undefined,
      });

      if (activeTreeKey !== 'ALL') {
        const catMap: Record<string, string> = {
          PROSEDUR: 'Prosedürler',
          TALIMAT: 'Talimatlar',
          FORM: 'Formlar',
          EL_KITABI: 'El Kitapları',
          POLITIKA: 'Politika & Yönetmelikler',
          SUREC: 'Süreç Kartları',
          DIGER: 'Diğer Dokümanlar',
        };
        crumbs.push({
          label: catMap[activeTreeKey] || activeTreeKey,
          onClick: activeDocCode ? () => setActiveDocCode(null) : undefined,
        });
      }
    }

    if (activeDocCode) {
      crumbs.push({ label: activeDocCode });
    }

    return crumbs;
  }, [activeTreeKey, activeDocCode]);

  // View state helpers
  const isMatrixView =
    activeTreeKey === 'CONFLICTS' ||
    activeTreeKey === 'GAPS' ||
    activeTreeKey === 'MISSING_REFS';

  const isDecisionsView = activeTreeKey === 'DECISIONS';

  return (
    <div className="kys-app-layout">
      {/* Left Navigation Tree */}
      <KysSidebar
        activeTreeKey={activeTreeKey}
        onSelectTreeKey={handleSelectTreeKey}
        stats={stats}
        conflictCount={conflictCount}
        gapCount={gapCount}
        missingRefsCount={missingRefsCount}
        decisionCount={decisionCount}
        docCountsByType={docCountsByType}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        onOpenSearch={() => setActiveToolModal('search')}
        onOpenAsk={() => setActiveToolModal('ask')}
        onOpenSettings={() => setShowSettings(true)}
      />

      {/* Main Content Viewport */}
      <div className="kys-main-viewport">
        {/* Top Header */}
        <KysHeader
          breadcrumbs={breadcrumbs}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          stats={stats}
          health={health}
          theme={theme}
          onToggleTheme={toggleTheme}
          onOpenSettings={() => setShowSettings(true)}
          onRefresh={refreshData}
          onRunAudit={handleRunAudit}
          onSelectTreeKey={handleSelectTreeKey}
          runningAudit={runningAudit}
          loading={loadingData}
          conflictCount={conflictCount}
          gapCount={gapCount}
          decisionCount={decisionCount}
        />

        {/* Content Area */}
        <main className="kys-content-area">
          {activeDocCode ? (
            // 1. Tabbed Document Detail & Conflict Analysis View
            <KysDocDetail
              code={activeDocCode}
              initialTab={docDetailInitialTab}
              onClose={handleCloseDoc}
              onOpenDoc={handleOpenDoc}
              onRefreshStats={refreshData}
            />
          ) : isDecisionsView ? (
            // 2. Decision Inventory & Authority Limits View
            <KysDecisionsTab
              documents={documents}
              findings={findings}
              onOpenDoc={handleOpenDoc}
              onRefreshData={refreshData}
            />
          ) : isMatrixView ? (
            // 3. Global Conflict & Gap Matrix View
            <KysAuditMatrix
              mode={activeTreeKey as 'CONFLICTS' | 'GAPS' | 'MISSING_REFS'}
              findings={findings}
              missingRefs={missingRefs}
              loading={loadingData}
              onRefresh={refreshData}
              onRunAudit={handleRunAudit}
              runningAudit={runningAudit}
              onOpenDoc={handleOpenDoc}
              onStatsChanged={refreshData}
            />
          ) : (
            // 4. High-Density Controlled Documents Data Grid
            <KysDocGrid
              documents={documents}
              findings={findings}
              loading={loadingData}
              error={dataError}
              activeTreeKey={activeTreeKey}
              searchQuery={searchQuery}
              onOpenDoc={(code) => handleOpenDoc(code, 'content')}
              onOpenConflictsForDoc={(code) => handleOpenDoc(code, 'conflicts')}
            />
          )}
        </main>
      </div>

      {/* Search / AI Ask Modal */}
      {activeToolModal && (
        <KysToolModal
          tool={activeToolModal}
          onClose={() => setActiveToolModal(null)}
          onOpenDoc={handleOpenDoc}
        />
      )}

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal
          onClose={() => setShowSettings(false)}
          onSaved={refreshData}
        />
      )}
    </div>
  );
};

export default App;
