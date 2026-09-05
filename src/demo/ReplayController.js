const SESSION_KEY = "twinops.demo.session.v1";
const commandId = () => globalThis.crypto.randomUUID();

/** Owns transport only. Every telemetry view receives the same server context. */
export class ReplayController {
  constructor(source, { storage, document: doc, interval = setInterval, clear = clearInterval } = {}) {
    this.source = source; this.storage = storage; this.document = doc;
    this.interval = interval; this.clear = clear; this.listeners = new Set(); this.epoch = 0;
    this.session = null; this.context = null; this.transport = null; this.rag = null; this.manual = null;
    this.eventResults = new Map(); this.retryAt = new Map(); this.hidden = Boolean(doc?.hidden);
    this.state = { context: null, datasets: [], loading: true, busy: false, error: null,
      suspended: false, events: [], manualPending: false, answers: [], assistantError: null,
      pendingOperation: null, queuedAction: null };
  }
  subscribe = (listener) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  getSnapshot = () => this.state;
  publish(patch) { this.state = { ...this.state, ...patch }; this.listeners.forEach((l) => l()); }
  accept(context, epoch) {
    if (epoch !== this.epoch || context.replay.runId !== this.session?.runId) return false;
    if (this.context && (context.replay.generation < this.context.replay.generation
      || context.revision < this.context.revision)) return false;
    if (this.context && context.replay.generation !== this.context.replay.generation) {
      this.rag?.abort(); this.manual?.abort(); this.eventResults.clear(); this.retryAt.clear();
      this.rag = null; this.manual = null;
      this.publish({ answers: [], assistantError: null, manualPending: false });
    }
    this.context = context;
    const events = context.events.map((event) => {
      const result = this.eventResults.get(event.eventId);
      if (["ready", "degraded"].includes(event.status)) { this.eventResults.delete(event.eventId); return event; }
      return result && result.generation === context.replay.generation ? result : event;
    });
    this.publish({ context, events }); return true;
  }
  async start() {
    const epoch = ++this.epoch;
    this.lifecycle = new AbortController();
    try {
      const datasets = await this.source.datasets({ signal: this.lifecycle.signal });
      if (epoch !== this.epoch) return;
      this.publish({ datasets });
      let saved;
      try { saved = JSON.parse(this.storage?.getItem(SESSION_KEY) ?? "null"); } catch { /* storage unavailable */ }
      if (saved && typeof saved.runId === "string" && typeof saved.token === "string") {
        this.session = saved;
        const context = await this.source.context(saved, { signal: this.lifecycle.signal });
        if (this.accept(context, epoch)) {
          this.publish({ suspended: context.replay.state === "running" });
          if (context.replay.state === "running") await this.command("pause");
        }
      }
    } catch (error) { if (epoch === this.epoch && error.name !== "AbortError") this.publish({ error: error.message }); }
    finally { if (epoch === this.epoch) this.publish({ loading: false }); }
    if (epoch !== this.epoch) return;
    this.timer = this.interval(() => this.tick(), 1000);
    this.visibility = () => {
      this.hidden = Boolean(this.document.hidden);
      if (this.hidden) {
        this.publish({ suspended: true });
        if (this.context?.replay.state === "running") this.command("pause");
      }
    };
    this.document?.addEventListener("visibilitychange", this.visibility);
  }
  dispose() {
    ++this.epoch; this.clear(this.timer); this.lifecycle?.abort(); this.transport?.abort();
    this.rag?.abort(); this.manual?.abort(); this.document?.removeEventListener("visibilitychange", this.visibility);
  }
  async create(datasetId, scenario = "guided", speed = 1) {
    const epoch = ++this.epoch;
    this.lifecycle?.abort(); this.transport?.abort(); this.rag?.abort(); this.manual?.abort();
    this.rag = null; this.manual = null; this.queued = null;
    this.context = null; this.session = null; this.eventResults.clear(); this.retryAt.clear();
    this.publish({ context: null, events: [], busy: true, error: null, answers: [], assistantError: null, manualPending: false, suspended: false, pendingOperation: "create", queuedAction: null });
    const controller = new AbortController(); this.transport = controller;
    try {
      const run = await this.source.create({ datasetId, scenario, speed }, { signal: controller.signal });
      if (epoch !== this.epoch) return;
      this.session = { runId: run.runId, token: run.token };
      try { this.storage?.setItem(SESSION_KEY, JSON.stringify(this.session)); } catch { /* replay can run without storage */ }
      this.accept(run.context, epoch);
    } catch (error) { if (epoch === this.epoch && error.name !== "AbortError") this.publish({ error: error.message }); }
    finally { if (this.transport === controller) { this.transport = null; this.publish({ busy: false, pendingOperation: null }); } }
  }
  async refresh() {
    if (!this.session) {
      try { this.publish({ datasets: await this.source.datasets(), error: null }); }
      catch (error) { this.publish({ error: error.message }); }
      return;
    }
    if (this.transport) return;
    const epoch = this.epoch; const controller = new AbortController(); this.transport = controller;
    this.publish({ busy: true, pendingOperation: "refresh" });
    try {
      const context = await this.source.context(this.session, { signal: controller.signal });
      if (this.accept(context, epoch)) this.publish({ error: null, suspended: true });
    } catch (error) { if (epoch === this.epoch && error.name !== "AbortError") this.publish({ error: error.message }); }
    finally { if (this.transport === controller) { this.transport = null; this.publish({ busy: false, pendingOperation: null }); } }
  }
  command(action, speed) {
    if (this.queued) return this.queued.promise;
    if (["pause", "restart"].includes(action)) {
      // Record the intent immediately; the current server transaction may already be committed.
      this.publish({ suspended: true });
      if (this.transport && this.state.pendingOperation === "advance") {
        const intent = { epoch: this.epoch, generation: this.context.replay.generation, action };
        this.queued = intent;
        this.publish({ queuedAction: action });
        intent.promise = (async () => {
          const sameGeneration = () => intent.epoch === this.epoch && intent.generation === this.context?.replay.generation;
          await this.inflight;
          if (!sameGeneration()) return;
          // On an ambiguous failure, read the committed revision before issuing the new intent.
          if (this.state.error) await this.refresh();
          if (!sameGeneration() || this.state.error) return;
          await this.transact("control", action, speed);
        })().finally(() => {
          if (this.queued === intent) { this.queued = null; this.publish({ queuedAction: null }); }
        });
        return intent.promise;
      }
    }
    return this.transact("control", action, speed);
  }
  transact(operation, action, speed) {
    if (!this.session || !this.context || this.transport) return Promise.resolve();
    const epoch = this.epoch, session = this.session;
    const controller = new AbortController(); this.transport = controller;
    const body = { commandId: commandId(), expectedRevision: this.context.revision,
      ...(action ? { action } : {}), ...(speed ? { speed } : {}) };
    this.publish({ busy: true, error: null, pendingOperation: operation });
    this.inflight = (async () => {
      try {
        const context = await this.source[operation](session, body, { signal: controller.signal });
        if (this.accept(context, epoch) && ["play", "resume", "restart"].includes(action)) {
          this.publish({ suspended: false });
        }
      } catch (error) {
        if (epoch !== this.epoch || error.name === "AbortError") return;
        this.publish({ error: error.message, suspended: true });
        if (error.status === 409) {
          try { this.accept(await this.source.context(session, { signal: controller.signal }), epoch); }
          catch { /* retain the known revision and recoverable error */ }
        }
      } finally {
        if (this.transport === controller) { this.transport = null; this.publish({ busy: false, pendingOperation: null }); }
      }
    })();
    return this.inflight;
  }
  tick() {
    if (!this.hidden && !this.state.suspended && !this.state.error && this.context?.replay.state === "running") this.transact("advance");
    if (!this.hidden) this.recommendNext();
  }
  async recommendNext() {
    if (this.rag || !this.session || !this.context) return;
    const event = this.state.events.find((e) => (e.status === "pending" || e.status === "processing" || e.retryable)
      && (this.retryAt.get(e.eventId) ?? 0) <= Date.now());
    if (!event) return;
    const epoch = this.epoch, generation = this.context.replay.generation;
    const controller = new AbortController(); this.rag = controller;
    this.retryAt.set(event.eventId, Date.now() + 5000);
    try {
      const result = await this.source.recommend(this.session, event.eventId, { signal: controller.signal });
      if (epoch !== this.epoch || generation !== this.context?.replay.generation) return;
      this.eventResults.set(event.eventId, result);
      this.publish({ events: this.state.events.map((e) => e.eventId === event.eventId ? result : e), assistantError: null });
    } catch (error) {
      if (epoch === this.epoch && generation === this.context?.replay.generation && error.name !== "AbortError") {
        this.publish({ assistantError: "Recomendação pendente. Nova tentativa automática em alguns segundos." });
      }
    } finally { if (this.rag === controller) this.rag = null; }
  }
  async query(question) {
    if (this.manual || !this.session || !this.context) return;
    const epoch = this.epoch, generation = this.context.replay.generation, revision = this.context.revision;
    const controller = new AbortController(); this.manual = controller;
    this.publish({ manualPending: true, assistantError: null });
    try {
      const answer = await this.source.query(this.session, { question, contextRevision: revision }, { signal: controller.signal });
      if (epoch !== this.epoch || generation !== this.context?.replay.generation) return;
      if (answer.contextRevision !== revision) throw new Error("Resposta rejeitada: revisão diferente da pergunta.");
      this.publish({ answers: [...this.state.answers, { ...answer, question }] });
    } catch (error) {
      if (epoch === this.epoch && generation === this.context?.replay.generation && error.name !== "AbortError") {
        this.publish({ assistantError: error.message });
        if (error.status === 409) await this.refresh();
      }
    } finally { if (this.manual === controller) { this.manual = null; this.publish({ manualPending: false }); } }
  }
}
