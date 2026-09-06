import React, { useEffect, useRef, useState } from "react";
import { formatDateTime } from "../../lib/displayTime.js";

const ADMIN_METHODS = [
  "createDraft",
  "uploadDocument",
  "getCorpus",
  "testRetrieval",
  "publish",
  "reactivate",
];

const INITIAL_CREATE = Object.freeze({
  chunkTargetTokens: "700",
  chunkOverlapTokens: "100",
  minRelevanceScore: "0.2",
});

const INITIAL_DOCUMENT = Object.freeze({
  manufacturer: "",
  equipmentModel: "",
  revision: "",
  language: "",
  sourceUrl: "",
});

const actionCopy = (kind) => kind === "publish"
  ? { noun: "publicação", verb: "publicação", confirm: "Confirmar publicação" }
  : { noun: "reativação", verb: "reativação", confirm: "Confirmar reativação" };

function Coverage({ value }) {
  if (!value) return <p className="empty-state">Envie um manual para calcular a cobertura do corpus.</p>;
  return (
    <dl className="rag-coverage" aria-label="Cobertura do corpus">
      <div>
        <dt>Cobertura textual</dt>
        <dd>{value.coveragePages} de {value.pageCount} páginas com texto</dd>
      </div>
      <div>
        <dt>Índice</dt>
        <dd>{value.chunkCount} chunks · {value.documentCount} {value.documentCount === 1 ? "documento" : "documentos"}</dd>
      </div>
    </dl>
  );
}

function Confirmation({ pending, onConfirm, onCancel, disabled, confirmButtonRef }) {
  if (!pending) return null;
  const copy = actionCopy(pending.kind);
  return (
    <aside
      className="rag-confirmation"
      role="alertdialog"
      aria-labelledby="rag-confirmation-title"
      aria-describedby="rag-confirmation-description"
    >
      <h3 id="rag-confirmation-title">
        Confirme a {copy.noun} do corpus {pending.corpusId}
      </h3>
      <p id="rag-confirmation-description">
        Esta ação trocará o ponteiro ativo do equipamento para o corpus {pending.corpusId}.
        Verifique o ID antes de continuar.
      </p>
      <div className="assistant-form__actions">
        <button ref={confirmButtonRef} type="button" onClick={onConfirm} disabled={disabled}>
          {copy.confirm} de {pending.corpusId}
        </button>
        <button type="button" className="button-secondary" onClick={onCancel} disabled={disabled}>
          Manter corpus atual
        </button>
      </div>
    </aside>
  );
}

export default function RagAdminPanel({ dataSource, assetId }) {
  if (!dataSource || ADMIN_METHODS.some((method) => typeof dataSource[method] !== "function")) {
    throw new TypeError("RagAdminPanel dataSource must implement the RAG admin contract");
  }
  if (typeof assetId !== "string" || assetId.length === 0) {
    throw new TypeError("RagAdminPanel assetId must be a non-empty string");
  }

  const [createValues, setCreateValues] = useState(INITIAL_CREATE);
  const [switchCorpusId, setSwitchCorpusId] = useState("");
  const [corpus, setCorpus] = useState(null);
  const [corpusCoverage, setCorpusCoverage] = useState(null);
  const [documentValues, setDocumentValues] = useState(INITIAL_DOCUMENT);
  const [file, setFile] = useState(null);
  const [uploadedDocument, setUploadedDocument] = useState(null);
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalItems, setRetrievalItems] = useState([]);
  const [confirmation, setConfirmation] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const controllersRef = useRef(new Set());
  const mountedRef = useRef(true);
  const confirmationButtonRef = useRef(null);
  const publishTriggerRef = useRef(null);
  const reactivateTriggerRef = useRef(null);
  const returnFocusRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      controllersRef.current.forEach((controller) => controller.abort());
      controllersRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (confirmation && busy === null) {
      confirmationButtonRef.current?.focus();
      return;
    }
    if (!confirmation && returnFocusRef.current) {
      returnFocusRef.current.focus();
      returnFocusRef.current = null;
    }
  }, [busy, confirmation]);

  const run = async (operation, action, onSuccess) => {
    const controller = new AbortController();
    controllersRef.current.add(controller);
    setBusy(operation);
    setError(null);
    setSuccess(null);
    try {
      const result = await action(controller.signal);
      if (!mountedRef.current || controller.signal.aborted) return;
      onSuccess(result);
    } catch (operationError) {
      if (mountedRef.current && operationError?.name !== "AbortError") {
        setError("A operação administrativa não pôde ser concluída. Revise os dados ou tente novamente.");
      }
    } finally {
      controllersRef.current.delete(controller);
      if (mountedRef.current) setBusy((current) => current === operation ? null : current);
    }
  };

  const createDraft = (event) => {
    event.preventDefault();
    void run("create", (signal) => dataSource.createDraft({
      assetId,
      chunkTargetTokens: Number(createValues.chunkTargetTokens),
      chunkOverlapTokens: Number(createValues.chunkOverlapTokens),
      minRelevanceScore: Number(createValues.minRelevanceScore),
    }, { signal }), (created) => {
      setCorpus(created);
      setCorpusCoverage(null);
      setUploadedDocument(null);
      setRetrievalItems([]);
      setConfirmation(null);
      setSuccess(`Draft ${created.corpusId} criado. Nenhum corpus foi publicado automaticamente.`);
    });
  };

  const loadCorpus = (event) => {
    event.preventDefault();
    const corpusId = switchCorpusId.trim();
    if (!corpusId) return;
    void run("switch", (signal) => dataSource.getCorpus(corpusId, { signal }), (result) => {
      setCorpus(result.corpus);
      setCorpusCoverage(result.coverage);
      setUploadedDocument(null);
      setRetrievalItems([]);
      setConfirmation(null);
      setSuccess(`Corpus ${result.corpus.corpusId} carregado para inspeção.`);
    });
  };

  const upload = (event) => {
    event.preventDefault();
    if (!corpus || !file) return;
    void run("upload", (signal) => dataSource.uploadDocument(corpus.corpusId, {
      file,
      ...documentValues,
    }, { signal }), (result) => {
      setUploadedDocument(result.document);
      setCorpusCoverage(result.coverage);
      setSuccess(`Manual ${result.document.documentId} extraído sem persistir o PDF original.`);
    });
  };

  const testRetrieval = (event) => {
    event.preventDefault();
    if (!corpus || !retrievalQuery.trim()) return;
    void run("retrieval", (signal) => dataSource.testRetrieval(corpus.corpusId, {
      query: retrievalQuery.trim(),
      limit: 6,
    }, { signal }), (result) => {
      setRetrievalItems(result.items);
      setSuccess(`${result.items.length} trechos recuperados para validação.`);
    });
  };

  const activate = () => {
    if (!confirmation || confirmation.corpusId !== corpus?.corpusId) return;
    const pending = confirmation;
    void run(pending.kind, (signal) => dataSource[pending.kind](pending.corpusId, { signal }), (result) => {
      setCorpus((current) => current && current.corpusId === result.corpusId
        ? { ...current, status: "published" }
        : current);
      setConfirmation(null);
      setSuccess(`Corpus ${result.corpusId} ativado em ${formatDateTime(result.activatedAt)} · São Paulo.`);
    });
  };

  const openConfirmation = (kind) => {
    const triggerRef = kind === "publish" ? publishTriggerRef : reactivateTriggerRef;
    returnFocusRef.current = triggerRef.current;
    setConfirmation({ kind, corpusId: corpus.corpusId });
  };

  const cancelConfirmation = () => {
    setConfirmation(null);
  };

  const updateCreate = (field) => (event) => {
    setCreateValues((current) => ({ ...current, [field]: event.target.value }));
  };
  const updateDocument = (field) => (event) => {
    setDocumentValues((current) => ({ ...current, [field]: event.target.value }));
  };

  return (
    <main className="rag-admin-shell">
      <header className="rag-admin-header">
        <div>
          <p className="eyebrow">Preview protegido · uso administrativo</p>
          <h1>Administração do RAG</h1>
        </div>
        <p>
          O backend continua sendo a autoridade de segurança. Upload e ativação não existem em produção.
        </p>
      </header>

      <div className="rag-admin-status" aria-live="polite" aria-atomic="true">
        {error ? <p className="warning-banner" role="alert">{error}</p> : null}
        {success ? <p className="success-banner" role="status">{success}</p> : null}
      </div>

      <section className="panel" aria-labelledby="rag-version-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Versões imutáveis</p>
            <h2 id="rag-version-title">Selecionar versão de trabalho</h2>
          </div>
        </div>
        <div className="rag-admin-form-grid">
          <form aria-label="Criar corpus draft" onSubmit={createDraft}>
            <h3>Novo draft</h3>
            <label htmlFor="rag-target-tokens">Tokens por chunk</label>
            <input id="rag-target-tokens" type="number" min="200" max="2000" required value={createValues.chunkTargetTokens} onChange={updateCreate("chunkTargetTokens")} />
            <label htmlFor="rag-overlap-tokens">Sobreposição</label>
            <input id="rag-overlap-tokens" type="number" min="0" max="500" required value={createValues.chunkOverlapTokens} onChange={updateCreate("chunkOverlapTokens")} />
            <label htmlFor="rag-relevance">Relevância mínima</label>
            <input id="rag-relevance" type="number" min="0" max="1" step="0.01" required value={createValues.minRelevanceScore} onChange={updateCreate("minRelevanceScore")} />
            <button type="submit" disabled={busy !== null}>{busy === "create" ? "Criando draft…" : "Criar corpus draft"}</button>
          </form>

          <form aria-label="Carregar outra versão de corpus" onSubmit={loadCorpus}>
            <h3>Inspecionar versão existente</h3>
            <label htmlFor="rag-corpus-switch">ID do corpus</label>
            <input id="rag-corpus-switch" required value={switchCorpusId} onChange={(event) => setSwitchCorpusId(event.target.value)} />
            <button type="submit" disabled={busy !== null || !switchCorpusId.trim()}>{busy === "switch" ? "Carregando corpus…" : "Carregar corpus"}</button>
          </form>
        </div>
      </section>

      {corpus ? (
        <>
          <section className="panel rag-corpus-summary" aria-labelledby="rag-corpus-title">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">{corpus.status}</p>
                <h2 id="rag-corpus-title">Corpus {corpus.corpusId}</h2>
              </div>
              <span className="quality-chip">{corpus.embeddingModel} · {corpus.embeddingDimensions}D</span>
            </div>
            <p>{corpus.manufacturer} · {corpus.equipmentModel}</p>
            <Coverage value={corpusCoverage} />
          </section>

          <section className="rag-admin-columns">
            <form className="panel rag-upload-form" aria-label="Enviar manual pesquisável" onSubmit={upload}>
              <p className="eyebrow">PDF pesquisável · até 25 MB / 400 páginas</p>
              <h2>Enviar manual</h2>
              <label htmlFor="rag-manual-file">Manual PDF</label>
              <input id="rag-manual-file" type="file" accept="application/pdf,.pdf" required onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              <label htmlFor="rag-manufacturer">Fabricante</label>
              <input id="rag-manufacturer" required value={documentValues.manufacturer} onChange={updateDocument("manufacturer")} />
              <label htmlFor="rag-equipment-model">Modelo do equipamento</label>
              <input id="rag-equipment-model" required value={documentValues.equipmentModel} onChange={updateDocument("equipmentModel")} />
              <label htmlFor="rag-revision">Revisão</label>
              <input id="rag-revision" required value={documentValues.revision} onChange={updateDocument("revision")} />
              <label htmlFor="rag-language">Idioma</label>
              <input id="rag-language" required value={documentValues.language} onChange={updateDocument("language")} />
              <label htmlFor="rag-source-url">URL oficial</label>
              <input id="rag-source-url" type="url" required value={documentValues.sourceUrl} onChange={updateDocument("sourceUrl")} />
              <button type="submit" disabled={busy !== null || !file}>{busy === "upload" ? "Extraindo e indexando…" : "Enviar e criar chunks"}</button>
              {uploadedDocument ? <p>Documento {uploadedDocument.documentId} · SHA-256 {uploadedDocument.sha256}</p> : null}
            </form>

            <form className="panel" aria-label="Testar recuperação do corpus" onSubmit={testRetrieval}>
              <p className="eyebrow">Antes de publicar</p>
              <h2>Consulta de validação</h2>
              <label htmlFor="rag-retrieval-query">Consulta de teste</label>
              <textarea id="rag-retrieval-query" maxLength={500} rows={4} required value={retrievalQuery} onChange={(event) => setRetrievalQuery(event.target.value)} />
              <button type="submit" disabled={busy !== null || !retrievalQuery.trim()}>{busy === "retrieval" ? "Buscando chunks…" : "Testar recuperação"}</button>
              <div className="rag-retrieval-results" aria-live="polite">
                {retrievalItems.map((item) => (
                  <details key={item.chunkId}>
                    <summary>Páginas {item.pageStart}–{item.pageEnd} · {item.section ?? "Seção não identificada"}</summary>
                    <blockquote>{item.excerpt}</blockquote>
                    <div className="rag-calibration-scores" aria-label={`Scores de calibração do chunk ${item.chunkId}`}>
                      <p>Score absoluto de relevância: {item.absoluteScore.toFixed(3)}</p>
                      <p>Score de ranking híbrido: {item.rankScore.toFixed(3)}</p>
                    </div>
                    <p>
                      Ranks: vetorial {item.vectorRank ?? "sem resultado"} · lexical {item.lexicalRank ?? "sem resultado"}
                    </p>
                    <code>SHA-256 {item.contentHash}</code>
                  </details>
                ))}
              </div>
            </form>
          </section>

          <section className="panel rag-activation" aria-labelledby="rag-activation-title">
            <p className="eyebrow">Gate explícito</p>
            <h2 id="rag-activation-title">Ativação atômica</h2>
            <p>Publicação e reativação exigem uma segunda confirmação com o ID exato.</p>
            <div className="assistant-form__actions">
              <button ref={publishTriggerRef} type="button" onClick={() => openConfirmation("publish")} disabled={busy !== null}>Publicar corpus</button>
              <button ref={reactivateTriggerRef} type="button" className="button-secondary" onClick={() => openConfirmation("reactivate")} disabled={busy !== null}>Reativar corpus</button>
            </div>
            <Confirmation
              pending={confirmation}
              onConfirm={activate}
              onCancel={cancelConfirmation}
              disabled={busy !== null}
              confirmButtonRef={confirmationButtonRef}
            />
          </section>
        </>
      ) : null}
    </main>
  );
}
