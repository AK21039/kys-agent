import {
  DocumentItem,
  SectionItem,
  DocumentDetail,
  DocumentSummary,
  SearchResult,
  ReferencesResponse,
  AskResponse,
  StatsResponse,
  Citation,
} from '../types/kys';
import {
  fold,
  codeKey,
  extractTerms,
  verifyQuote,
  looksLikeDocCode,
} from '../utils/textnorm';

const STORAGE_KEY = 'kys_published_db';

class KysStore {
  private documents: DocumentItem[] = [];

  constructor() {
    this.init();
  }

  private init() {
    this.documents = [];
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) {
          this.documents = parsed;
        }
      }
    } catch {
      this.documents = [];
    }
  }

  public hasDocuments(): boolean {
    return this.documents.length > 0;
  }

  public importDatabase(docs: DocumentItem[]): { success: boolean; count: number; error?: string } {
    if (!Array.isArray(docs)) {
      return { success: false, count: 0, error: 'Geçersiz veri formatı. Bir doküman dizisi bekleniyor.' };
    }

    const validated: DocumentItem[] = [];
    for (const d of docs) {
      if (!d.code || !d.title) continue;
      validated.push({
        id: d.id || validated.length + 1,
        code: String(d.code).trim(),
        code_key: codeKey(d.code),
        revision: String(d.revision ?? '00').trim(),
        title: String(d.title).trim(),
        doc_type: d.doc_type || 'DIGER',
        status: d.status || 'YURURLUKTE',
        revision_date: d.revision_date || null,
        effective_date: d.effective_date || null,
        owner_unit: d.owner_unit || null,
        summary: d.summary || null,
        parse_warnings: Array.isArray(d.parse_warnings) ? d.parse_warnings : [],
        sections: Array.isArray(d.sections)
          ? d.sections.map((s, idx) => ({
              id: s.id || idx + 1,
              document_id: d.id || validated.length + 1,
              ordinal: s.ordinal || idx + 1,
              clause_no: s.clause_no || null,
              heading: s.heading || null,
              heading_path: s.heading_path || null,
              text: String(s.text || ''),
            }))
          : [],
        references: Array.isArray(d.references)
          ? d.references.map((r) => ({
              ref_code: String(r.ref_code || ''),
              target_code: r.target_code || null,
              target_title: r.target_title || null,
              target_status: r.target_status || null,
            }))
          : [],
        referenced_by: Array.isArray(d.referenced_by)
          ? d.referenced_by.map((rb) => ({
              code: String(rb.code || ''),
              title: String(rb.title || ''),
            }))
          : [],
      });
    }

    this.documents = validated;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(validated));
    } catch {
      // localStorage quota
    }

    return { success: true, count: validated.length };
  }

  public clearDatabase(): void {
    this.documents = [];
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }

  public getStats(): StatsResponse {
    const active = this.documents.filter((d) => d.status === 'YURURLUKTE');
    const by_type: Record<string, number> = {};
    for (const d of active) {
      by_type[d.doc_type] = (by_type[d.doc_type] || 0) + 1;
    }
    const totalSections = this.documents.reduce((acc, d) => acc + d.sections.length, 0);
    const refs = this.getReferences();
    const unresolved_count = refs.missing_documents.length + refs.probably_not_documents.length;

    const dates = this.documents
      .map((d) => d.revision_date || '')
      .filter(Boolean)
      .sort()
      .reverse();
    const last_update = dates[0] || '';

    return {
      documents: active.length,
      by_type,
      sections: totalSections,
      unresolved_references: unresolved_count,
      last_update,
    };
  }

  public getDocuments(docType?: string): DocumentSummary[] {
    let list = this.documents.filter((d) => d.status === 'YURURLUKTE');
    if (docType && docType.trim()) {
      const targetType = docType.trim().toUpperCase();
      list = list.filter((d) => d.doc_type.toUpperCase() === targetType);
    }
    list.sort((a, b) => a.doc_type.localeCompare(b.doc_type) || a.code.localeCompare(b.code));

    return list.map((d) => ({
      code: d.code,
      revision: d.revision,
      title: d.title,
      doc_type: d.doc_type,
      status: d.status,
      revision_date: d.revision_date,
      owner_unit: d.owner_unit,
      summary: d.summary,
    }));
  }

  public getDocument(code: string): DocumentDetail | null {
    const targetKey = codeKey(code);
    const doc = this.documents.find((d) => d.code_key === targetKey || codeKey(d.code) === targetKey);
    if (!doc) {
      return null;
    }

    const referenced_by = this.documents
      .filter((other) =>
        other.code !== doc.code &&
        other.references.some((r) => codeKey(r.ref_code) === targetKey || codeKey(r.target_code || '') === targetKey)
      )
      .map((other) => ({ code: other.code, title: other.title }));

    const resolvedReferences = doc.references.map((r) => {
      const refTargetKey = codeKey(r.ref_code);
      const targetDoc = this.documents.find((d) => d.code_key === refTargetKey);
      return {
        ref_code: r.ref_code,
        target_code: targetDoc ? targetDoc.code : null,
        target_title: targetDoc ? targetDoc.title : null,
        target_status: targetDoc ? targetDoc.status : null,
      };
    });

    return {
      code: doc.code,
      revision: doc.revision,
      title: doc.title,
      doc_type: doc.doc_type,
      status: doc.status,
      revision_date: doc.revision_date || null,
      effective_date: doc.effective_date || null,
      owner_unit: doc.owner_unit || null,
      summary: doc.summary || null,
      warnings: doc.parse_warnings || [],
      sections: doc.sections.map((s) => ({
        id: s.id,
        clause_no: s.clause_no,
        heading: s.heading,
        heading_path: s.heading_path,
        text: s.text,
      })),
      references: resolvedReferences,
      referenced_by,
    };
  }

  public search(query: string, limit = 20): SearchResult[] {
    if (this.documents.length === 0) {
      return [];
    }

    const terms = extractTerms(query);
    if (!terms.length) {
      return [];
    }

    const results: SearchResult[] = [];
    const queryFolded = fold(query);

    for (const doc of this.documents) {
      if (doc.status !== 'YURURLUKTE') continue;

      for (const sec of doc.sections) {
        const secText = sec.text;
        const heading = sec.heading || '';
        const combined = `${heading} ${secText}`;
        const combinedFolded = fold(combined);

        let score = 0;

        if (combinedFolded.includes(queryFolded)) {
          score += 15;
        }

        let matchCount = 0;
        for (const term of terms) {
          if (combinedFolded.includes(term)) {
            matchCount++;
            if (fold(heading).includes(term)) {
              score += 5;
            } else {
              score += 2;
            }
          }
        }

        if (matchCount > 0) {
          score += matchCount * 2;
          results.push({
            code: doc.code,
            revision: doc.revision,
            title: doc.title,
            clause_no: sec.clause_no,
            heading: sec.heading,
            section_id: sec.id,
            text: secText.length > 500 ? secText.slice(0, 500) + '…' : secText,
            score,
          });
        }
      }
    }

    results.sort((a, b) => (b.score || 0) - (a.score || 0));
    return results.slice(0, limit);
  }

  public getReferences(): ReferencesResponse {
    if (this.documents.length === 0) {
      return {
        missing_documents: [],
        probably_not_documents: [],
      };
    }

    const activeCodes = new Set(this.documents.map((d) => d.code_key));
    const unresolvedMap = new Map<string, Set<string>>();

    for (const doc of this.documents) {
      for (const r of doc.references) {
        const refKey = codeKey(r.ref_code);
        if (!activeCodes.has(refKey)) {
          if (!unresolvedMap.has(r.ref_code)) {
            unresolvedMap.set(r.ref_code, new Set());
          }
          unresolvedMap.get(r.ref_code)!.add(doc.code);
        }
      }
    }

    const missing_documents: { code: string; referenced_from: string[] }[] = [];
    const probably_not_documents: string[] = [];

    unresolvedMap.forEach((sourcesSet, refCode) => {
      const sources = Array.from(sourcesSet).sort();
      if (looksLikeDocCode(refCode)) {
        missing_documents.push({
          code: refCode,
          referenced_from: sources,
        });
      } else {
        probably_not_documents.push(refCode);
      }
    });

    missing_documents.sort((a, b) => a.code.localeCompare(b.code));
    probably_not_documents.sort();

    return {
      missing_documents,
      probably_not_documents,
    };
  }

  public retrieveForQuestion(question: string, limit = 8): {
    section: SectionItem;
    doc: DocumentItem;
  }[] {
    if (this.documents.length === 0) {
      return [];
    }

    const qFolded = fold(question);
    const rows: { section: SectionItem; doc: DocumentItem; score: number }[] = [];
    const seenSectionIds = new Set<number>();

    // 1. Dokümanda adı geçen dokümanlar
    for (const doc of this.documents) {
      if (doc.status !== 'YURURLUKTE') continue;
      const codeMatches = qFolded.includes(fold(doc.code)) || qFolded.includes(doc.code_key);
      const titleFolded = fold(doc.title);
      const titleMatches = titleFolded.length >= 8 && qFolded.includes(titleFolded);

      if (codeMatches || titleMatches) {
        for (const s of doc.sections) {
          if (!seenSectionIds.has(s.id)) {
            seenSectionIds.add(s.id);
            rows.push({ section: s, doc, score: 100 });
          }
        }
      }
    }

    // 2. Anahtar kelimeler
    const terms = extractTerms(question);
    if (terms.length > 0) {
      for (const doc of this.documents) {
        if (doc.status !== 'YURURLUKTE') continue;
        for (const s of doc.sections) {
          if (seenSectionIds.has(s.id)) continue;

          const combined = fold(`${s.heading || ''} ${s.text}`);
          let score = 0;
          for (const t of terms) {
            if (combined.includes(t)) {
              score += 3;
            }
          }
          if (score > 0) {
            seenSectionIds.add(s.id);
            rows.push({ section: s, doc, score });
          }
        }
      }
    }

    rows.sort((a, b) => b.score - a.score);
    return rows.slice(0, limit);
  }

  public async askQuestion(question: string): Promise<AskResponse> {
    const cleanQ = question.trim();
    if (!cleanQ) {
      return {
        answer: 'Soru belirtilmedi.',
        yeterli_bilgi: false,
        citations: [],
        unverified: 0,
        sources: [],
        model: 'kys-retrieval',
      };
    }

    if (this.documents.length === 0) {
      return {
        answer: 'Sistemde henüz yüklenmiş veya onaylanmış bir Kalite Yönetim Sistemi dokümanı bulunmamaktadır. Cevap üretilebilmesi için onaylı doküman veritabanı yüklenmelidir.',
        yeterli_bilgi: false,
        citations: [],
        unverified: 0,
        sources: [],
        model: 'kys-retrieval',
      };
    }

    const candidateRows = this.retrieveForQuestion(cleanQ, 8);
    const sources = candidateRows.map((item, idx) => ({
      no: idx + 1,
      section_id: item.section.id,
      code: item.doc.code,
      revision: item.doc.revision,
      clause_no: item.section.clause_no,
      heading: item.section.heading,
      title: item.doc.title,
    }));

    if (candidateRows.length === 0) {
      return {
        answer: 'Bu soruyla ilgili yürürlükteki onaylı dokümanlar arasında eşleşen bir bölüm bulunamadı.',
        yeterli_bilgi: false,
        citations: [],
        unverified: 0,
        sources: [],
        model: 'kys-retrieval',
      };
    }

    // Gerçek metinden kanıta dayalı alıntı oluşturma (CLAUDE.md Invariant 1: Kanıtsız bulgu yok)
    const top = candidateRows[0];
    const no = 1;
    const clauseRef = top.section.clause_no ? `md.${top.section.clause_no}` : '';
    const answer = `Onaylı doküman (${top.doc.code} Rev.${top.doc.revision} ${clauseRef}) içeriğine göre [${no}]:\n${top.section.text}`;

    const sentences = top.section.text.split(/(?<=[.!?])\s+/);
    const validSentence = sentences.find((s) => s.trim().length >= 12) || top.section.text.slice(0, 150);

    const verifiedCitations: Citation[] = [];
    let unverified = 0;

    const fullSourceText = `${top.section.heading || ''}\n${top.section.text}`;
    if (validSentence && verifyQuote(validSentence, fullSourceText)) {
      verifiedCitations.push({
        no,
        code: top.doc.code,
        revision: top.doc.revision,
        clause_no: top.section.clause_no,
        heading: top.section.heading,
        title: top.doc.title,
        quote: validSentence,
        section_id: top.section.id,
      });
    } else {
      unverified++;
    }

    return {
      answer,
      yeterli_bilgi: verifiedCitations.length > 0,
      citations: verifiedCitations,
      unverified,
      sources,
      model: 'kys-retrieval',
    };
  }
}

export const kysStore = new KysStore();
