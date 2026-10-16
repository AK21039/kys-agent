import React, { useState } from 'react';
import { SearchResult } from '../types/kys';
import { kysStore } from '../services/kysStore';

interface SearchTabProps {
  onOpenDoc: (code: string) => void;
  hasDocuments: boolean;
}

export const SearchTab: React.FC<SearchTabProps> = ({ onOpenDoc, hasDocuments }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);

  const handleSearch = (qStr?: string) => {
    const q = (qStr !== undefined ? qStr : query).trim();
    if (!q) return;
    const res = kysStore.search(q, 20);
    setResults(res);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSearch();
  };

  return (
    <section id="tab-search">
      <form onSubmit={handleSubmit}>
        <input
          id="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Aranacak ifade veya doküman kodu..."
          disabled={!hasDocuments}
        />
        <button type="submit" disabled={!hasDocuments || !query.trim()}>
          Ara
        </button>
      </form>

      {!hasDocuments && (
        <div className="card warn">
          Arama yapılacak kayıtlı doküman bulunmuyor.
        </div>
      )}

      <div id="search-out">
        {results !== null && hasDocuments && (
          results.length > 0 ? (
            results.map((r, i) => (
              <div key={i} className="card">
                <span
                  className="ref"
                  onClick={() => onOpenDoc(r.code)}
                >
                  {r.code} Rev.{r.revision}
                  {r.clause_no ? ` md.${r.clause_no}` : ''}
                </span>{' '}
                <span className="meta">
                  {r.title}
                  {r.heading ? ` · ${r.heading}` : ''}
                </span>
                <pre>{r.text}</pre>
              </div>
            ))
          ) : (
            <div className="meta">Sonuç yok.</div>
          )
        )}
      </div>
    </section>
  );
};
