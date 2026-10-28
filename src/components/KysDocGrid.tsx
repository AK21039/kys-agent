import React, { useState, useMemo } from 'react';
import {
  FileText,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { DocumentSummary, FindingItem } from '../types/kys';

export interface KysDocGridProps {
  documents: DocumentSummary[];
  findings: FindingItem[];
  loading: boolean;
  error: string | null;
  activeTreeKey: string;
  searchQuery: string;
  onOpenDoc: (code: string) => void;
  onOpenConflictsForDoc?: (code: string) => void;
}

type SortField = 'code' | 'title' | 'doc_type' | 'revision' | 'status' | 'effective_date' | 'findings';
type SortDirection = 'asc' | 'desc';

export const KysDocGrid: React.FC<KysDocGridProps> = ({
  documents,
  findings,
  loading,
  error,
  activeTreeKey,
  searchQuery,
  onOpenDoc,
  onOpenConflictsForDoc,
}) => {
  const [statusFilter, setStatusFilter] = useState<string>('HEPSI');
  const [sortField, setSortField] = useState<SortField>('code');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Compute map of document findings
  const docFindingsMap = useMemo(() => {
    const map: Record<string, { conflicts: FindingItem[]; gaps: FindingItem[] }> = {};
    findings.forEach((f) => {
      const code = f.document_code;
      if (!code) return;
      if (!map[code]) {
        map[code] = { conflicts: [], gaps: [] };
      }
      if (f.finding_type === 'CAKISMA' || f.finding_type === 'YETKI_ASIMI') {
        map[code].conflicts.push(f);
      } else {
        map[code].gaps.push(f);
      }
    });
    return map;
  }, [findings]);

  // Filter documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // 1. Category / Tree filter
      if (activeTreeKey !== 'ALL') {
        if (activeTreeKey === 'PROSEDUR' && doc.doc_type !== 'PROSEDUR') return false;
        if (activeTreeKey === 'TALIMAT' && doc.doc_type !== 'TALIMAT') return false;
        if (activeTreeKey === 'FORM' && doc.doc_type !== 'FORM') return false;
        if (activeTreeKey === 'EL_KITABI' && doc.doc_type !== 'EL_KITABI') return false;
        if (activeTreeKey === 'POLITIKA' && doc.doc_type !== 'POLITIKA' && doc.doc_type !== 'YONETMELIK') return false;
        if (activeTreeKey === 'SUREC' && doc.doc_type !== 'SUREC' && doc.doc_type !== 'PROSES_KARTI') return false;
        if (activeTreeKey === 'DIGER') {
          const mainTypes = ['PROSEDUR', 'TALIMAT', 'FORM', 'EL_KITABI', 'POLITIKA', 'YONETMELIK', 'SUREC', 'PROSES_KARTI'];
          if (mainTypes.includes(doc.doc_type)) return false;
        }
      }

      // 2. Status filter
      if (statusFilter !== 'HEPSI') {
        if (doc.status !== statusFilter) return false;
      }

      // 3. Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const codeMatch = doc.code?.toLowerCase().includes(q);
        const titleMatch = doc.title?.toLowerCase().includes(q);
        const unitMatch = doc.owner_unit?.toLowerCase().includes(q);
        const summaryMatch = doc.summary?.toLowerCase().includes(q);
        if (!codeMatch && !titleMatch && !unitMatch && !summaryMatch) {
          return false;
        }
      }

      return true;
    });
  }, [documents, activeTreeKey, statusFilter, searchQuery]);

  // Sort documents
  const sortedDocuments = useMemo(() => {
    const copy = [...filteredDocuments];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortField === 'code') {
        cmp = (a.code || '').localeCompare(b.code || '');
      } else if (sortField === 'title') {
        cmp = (a.title || '').localeCompare(b.title || '');
      } else if (sortField === 'doc_type') {
        cmp = (a.doc_type || '').localeCompare(b.doc_type || '');
      } else if (sortField === 'revision') {
        cmp = (a.revision || '').localeCompare(b.revision || '');
      } else if (sortField === 'status') {
        cmp = (a.status || '').localeCompare(b.status || '');
      } else if (sortField === 'effective_date') {
        cmp = (a.effective_date || a.revision_date || '').localeCompare(
          b.effective_date || b.revision_date || ''
        );
      } else if (sortField === 'findings') {
        const aCount = (docFindingsMap[a.code]?.conflicts.length || 0) + (docFindingsMap[a.code]?.gaps.length || 0);
        const bCount = (docFindingsMap[b.code]?.conflicts.length || 0) + (docFindingsMap[b.code]?.gaps.length || 0);
        cmp = aCount - bCount;
      }
      return sortDirection === 'asc' ? cmp : -cmp;
    });
    return copy;
  }, [filteredDocuments, sortField, sortDirection, docFindingsMap]);

  const handleHeaderSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const renderSortIndicator = (field: SortField) => {
    if (sortField !== field) {
      return <ArrowUpDown size={12} className="kys-sort-icon neutral" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp size={12} className="kys-sort-icon active" />
    ) : (
      <ArrowDown size={12} className="kys-sort-icon active" />
    );
  };

  const getCategoryTitle = () => {
    switch (activeTreeKey) {
      case 'PROSEDUR':
        return 'Prosedürler (PR)';
      case 'TALIMAT':
        return 'Talimatlar (TL)';
      case 'FORM':
        return 'Formlar & Raporlar (FR)';
      case 'EL_KITABI':
        return 'El Kitapları & Kılavuzlar';
      case 'POLITIKA':
        return 'Politikalar & Yönetmelikler';
      case 'SUREC':
        return 'Süreç & Akış Kartları';
      case 'DIGER':
        return 'Diğer Kontrollü Dokümanlar';
      default:
        return 'Tüm Kontrollü Dokümanlar Kataloğu';
    }
  };

  return (
    <div className="kys-grid-wrapper">
      {/* Table Toolbar */}
      <div className="kys-grid-toolbar">
        <div className="kys-grid-title-group">
          <FileText size={16} className="text-accent" />
          <h2 className="kys-grid-title">{getCategoryTitle()}</h2>
          <span className="kys-grid-count font-mono">
            {filteredDocuments.length} doküman
          </span>
        </div>

        <div className="kys-grid-filters">
          <div className="kys-status-segmented" role="radiogroup" aria-label="Durum Filtresi">
            <button
              type="button"
              className={`kys-seg-btn ${statusFilter === 'HEPSI' ? 'active' : ''}`}
              onClick={() => setStatusFilter('HEPSI')}
            >
              Tümü
            </button>
            <button
              type="button"
              className={`kys-seg-btn ${statusFilter === 'YURURLUKTE' ? 'active' : ''}`}
              onClick={() => setStatusFilter('YURURLUKTE')}
            >
              Yürürlükte
            </button>
            <button
              type="button"
              className={`kys-seg-btn ${statusFilter === 'REVIZYONDA' ? 'active' : ''}`}
              onClick={() => setStatusFilter('REVIZYONDA')}
            >
              Revizyonda
            </button>
            <button
              type="button"
              className={`kys-seg-btn ${statusFilter === 'IPTAL' ? 'active' : ''}`}
              onClick={() => setStatusFilter('IPTAL')}
            >
              İptal
            </button>
          </div>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="kys-alert-banner danger">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Grid Container */}
      <div className="kys-table-container">
        <table className="kys-table" aria-label="Kontrollü Dokümanlar Tablosu">
          <thead>
            <tr>
              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('code')}
                style={{ width: '130px' }}
              >
                <div className="kys-th-content">
                  <span>DOKÜMAN KODU</span>
                  {renderSortIndicator('code')}
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('title')}
              >
                <div className="kys-th-content">
                  <span>DOKÜMAN ADI / BAŞLIK</span>
                  {renderSortIndicator('title')}
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('doc_type')}
                style={{ width: '130px' }}
              >
                <div className="kys-th-content">
                  <span>TÜR</span>
                  {renderSortIndicator('doc_type')}
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('revision')}
                style={{ width: '80px', textAlign: 'center' }}
              >
                <div className="kys-th-content" style={{ justifyContent: 'center' }}>
                  <span>REV</span>
                  {renderSortIndicator('revision')}
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('status')}
                style={{ width: '110px' }}
              >
                <div className="kys-th-content">
                  <span>DURUM</span>
                  {renderSortIndicator('status')}
                </div>
              </th>

              <th scope="col" className="kys-th" style={{ width: '160px' }}>
                <div className="kys-th-content">
                  <span>SORUMLU BİRİM</span>
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('effective_date')}
                style={{ width: '110px' }}
              >
                <div className="kys-th-content">
                  <span>YÜRÜRLÜK</span>
                  {renderSortIndicator('effective_date')}
                </div>
              </th>

              <th
                scope="col"
                className="kys-th sortable"
                onClick={() => handleHeaderSort('findings')}
                style={{ width: '180px' }}
              >
                <div className="kys-th-content">
                  <span>ÇELİŞKİ / AÇIK NOKTA</span>
                  {renderSortIndicator('findings')}
                </div>
              </th>

              <th scope="col" className="kys-th" style={{ width: '80px', textAlign: 'right' }}>
                <span>İŞLEM</span>
              </th>
            </tr>
          </thead>

          <tbody>
            {loading ? (
              Array.from({ length: 7 }).map((_, idx) => (
                <tr key={idx} className="kys-skeleton-row">
                  <td colSpan={9}>
                    <div className="kys-skeleton-bar" />
                  </td>
                </tr>
              ))
            ) : sortedDocuments.length === 0 ? (
              <tr>
                <td colSpan={9} className="kys-empty-cell">
                  <div className="kys-empty-box">
                    <FileText size={28} className="text-muted" />
                    <p className="kys-empty-title">Kriterlere uygun doküman bulunamadı.</p>
                    <p className="kys-empty-sub">
                      Arama terimini temizleyebilir veya sol ağaçtan farklı bir kategori seçebilirsiniz.
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              sortedDocuments.map((doc) => {
                const docFindings = docFindingsMap[doc.code] || { conflicts: [], gaps: [] };
                const conflictCount = docFindings.conflicts.length;
                const gapCount = docFindings.gaps.length;
                const hasIssues = conflictCount > 0 || gapCount > 0;

                return (
                  <tr
                    key={doc.code}
                    className={`kys-table-row ${hasIssues ? 'has-findings' : ''}`}
                    onClick={() => onOpenDoc(doc.code)}
                  >
                    {/* Code */}
                    <td className="kys-td font-mono font-bold text-accent kys-code-cell">
                      <button
                        type="button"
                        className="kys-code-link"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenDoc(doc.code);
                        }}
                      >
                        {doc.code}
                      </button>
                    </td>

                    {/* Title */}
                    <td className="kys-td kys-title-cell">
                      <span className="kys-doc-name">{doc.title}</span>
                      {doc.summary && (
                        <span className="kys-doc-summary-hint">{doc.summary}</span>
                      )}
                    </td>

                    {/* Doc Type */}
                    <td className="kys-td text-muted text-xs">
                      {doc.doc_type}
                    </td>

                    {/* Revision */}
                    <td className="kys-td font-mono text-center text-xs">
                      {doc.revision || '00'}
                    </td>

                    {/* Status */}
                    <td className="kys-td">
                      <span className={`kys-status-label ${doc.status?.toLowerCase()}`}>
                        {doc.status === 'YURURLUKTE'
                          ? 'Yürürlükte'
                          : doc.status === 'REVIZYONDA'
                          ? 'Revizyonda'
                          : doc.status === 'IPTAL'
                          ? 'İptal'
                          : doc.status}
                      </span>
                    </td>

                    {/* Owner Unit */}
                    <td className="kys-td text-xs text-muted">
                      {doc.owner_unit || '—'}
                    </td>

                    {/* Date */}
                    <td className="kys-td font-mono text-xs text-muted">
                      {doc.effective_date || doc.revision_date || '—'}
                    </td>

                    {/* Conflicts & Gaps Badge */}
                    <td className="kys-td">
                      {conflictCount > 0 ? (
                        <button
                          type="button"
                          className="kys-finding-tag danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            if (onOpenConflictsForDoc) {
                              onOpenConflictsForDoc(doc.code);
                            } else {
                              onOpenDoc(doc.code);
                            }
                          }}
                          title={`${conflictCount} kural çelişkisi tespit edildi`}
                        >
                          <ShieldAlert size={12} />
                          <span>{conflictCount} Çakışma</span>
                        </button>
                      ) : gapCount > 0 ? (
                        <button
                          type="button"
                          className="kys-finding-tag warn"
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenDoc(doc.code);
                          }}
                          title={`${gapCount} açık nokta / süreç boşluğu tespit edildi`}
                        >
                          <AlertTriangle size={12} />
                          <span>{gapCount} Açık Nokta</span>
                        </button>
                      ) : (
                        <span className="kys-clean-label">
                          <CheckCircle2 size={12} className="text-ok" />
                          <span>Uyumlu</span>
                        </span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="kys-td text-right">
                      <button
                        type="button"
                        className="kys-row-action-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          onOpenDoc(doc.code);
                        }}
                        title="Dokümanı ve Çelişkileri İncele"
                      >
                        <ExternalLink size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
