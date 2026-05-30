/* ResearchRadar — browser-local personal memory graph (Dexie/IndexedDB)
 *
 * Privacy by design: a user's personal research graph lives in their browser.
 * Only a compact, derived context is ever sent to the backend agents.
 *
 * Exposes window.PersonalGraph with a small async API.
 */
(function () {
  "use strict";

  if (typeof Dexie === "undefined") {
    console.warn("[PersonalGraph] Dexie not loaded; personal graph disabled.");
    window.PersonalGraph = { available: false };
    return;
  }

  const db = new Dexie("researchradar_personal");
  db.version(1).stores({
    entities:        "++id, type, name, normalizedName, createdAt, updatedAt",
    edges:           "++id, sourceId, relation, targetId, createdAt",
    interactions:    "++id, paperId, type, value, createdAt",
    directives:      "++id, name, status, createdAt, updatedAt",
    collections:     "++id, name, createdAt, updatedAt",
    collectionItems: "++id, collectionId, paperId, createdAt",
    notes:           "++id, entityId, createdAt, updatedAt",
    preferences:     "key",
  });

  const now = () => new Date().toISOString();
  const norm = (s) => (s || "").toString().trim().toLowerCase();

  async function init() {
    try {
      await db.open();
      // Ensure a singleton "me" user entity exists
      await getOrCreateUserEntity();
      return true;
    } catch (e) {
      console.error("[PersonalGraph] init failed:", e);
      return false;
    }
  }

  async function getOrCreateUserEntity() {
    let me = await db.entities.where({ type: "user" }).first();
    if (!me) {
      const id = await db.entities.add({
        type: "user", name: "me", normalizedName: "me",
        createdAt: now(), updatedAt: now(),
      });
      me = await db.entities.get(id);
    }
    return me;
  }

  async function upsertEntity(type, name, extra = {}) {
    const normalizedName = norm(name);
    let ent = await db.entities.where({ normalizedName }).first();
    if (ent) {
      await db.entities.update(ent.id, { updatedAt: now(), ...extra });
      return ent.id;
    }
    return db.entities.add({ type, name, normalizedName, createdAt: now(), updatedAt: now(), ...extra });
  }

  async function addEdge(sourceId, relation, targetId) {
    return db.edges.add({ sourceId, relation, targetId, createdAt: now() });
  }

  async function recordInteraction(paperId, type, value = 1, metadata = {}) {
    if (!paperId) return null;
    return db.interactions.add({
      paperId: String(paperId), type, value,
      metadata: JSON.stringify(metadata || {}), createdAt: now(),
    });
  }

  async function savePaper(paper) {
    const pid = String(paper.id || paper.arxiv_id || paper._db_id);
    await recordInteraction(pid, "saved", 1, { title: paper.title, cat: paper.cat });
    const eId = await upsertEntity("paper", paper.title || pid, { paperId: pid, cat: paper.cat });
    const me  = await getOrCreateUserEntity();
    await addEdge(me.id, "saved", eId);
    // index topics/methods as entities linked to the paper
    (paper.tags || []).concat(paper.methods || []).forEach(async (t) => {
      const tId = await upsertEntity("topic", t);
      await addEdge(eId, "about", tId);
      await addEdge(me.id, "interested_in", tId);
    });
    return pid;
  }

  async function ignorePaper(paper) {
    const pid = String(paper.id || paper.arxiv_id || paper._db_id);
    await recordInteraction(pid, "ignored", -1, { title: paper.title });
    return pid;
  }

  async function moreLikeThis(paper) {
    const pid = String(paper.id || paper.arxiv_id || paper._db_id);
    await recordInteraction(pid, "more_like_this", 2, { title: paper.title });
    (paper.tags || []).concat(paper.methods || []).forEach(async (t) => {
      const tId = await upsertEntity("topic", t);
      const me  = await getOrCreateUserEntity();
      await addEdge(me.id, "boost", tId);
    });
    return pid;
  }

  async function lessLikeThis(paper) {
    const pid = String(paper.id || paper.arxiv_id || paper._db_id);
    await recordInteraction(pid, "less_like_this", -2, { title: paper.title });
    return pid;
  }

  async function getSavedPapers() {
    const rows = await db.interactions.where({ type: "saved" }).toArray();
    // de-dup by paperId, keep latest
    const map = {};
    rows.forEach((r) => { map[r.paperId] = r; });
    return Object.values(map);
  }

  async function getIgnoredPaperIds() {
    const rows = await db.interactions.where({ type: "ignored" }).toArray();
    return [...new Set(rows.map((r) => r.paperId))];
  }

  async function getRecentInteractions(limit = 50) {
    const rows = await db.interactions.orderBy("createdAt").reverse().limit(limit).toArray();
    return rows;
  }

  async function getTopInterests(limit = 12) {
    // Aggregate interest weights from interactions' topics
    const edges = await db.edges.where("relation").anyOf(["interested_in", "boost"]).toArray();
    const counts = {};
    for (const e of edges) {
      const ent = await db.entities.get(e.targetId);
      if (ent) counts[ent.name] = (counts[ent.name] || 0) + (e.relation === "boost" ? 2 : 1);
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, limit)
      .map(([name, weight]) => ({ name, weight }));
  }

  async function getPersonalContextForAgent() {
    const [saved, ignored, recent, interests, prefsArr] = await Promise.all([
      getSavedPapers(), getIgnoredPaperIds(), getRecentInteractions(30), getTopInterests(), db.preferences.toArray(),
    ]);
    const preferences = {};
    prefsArr.forEach((p) => { preferences[p.key] = p.value; });
    return {
      saved_papers:        saved.map((s) => s.paperId),
      ignored_paper_ids:   ignored,
      recent_interactions: recent.map((r) => ({ paperId: r.paperId, type: r.type, value: r.value })),
      saved_topics:        interests.map((i) => i.name),
      preferences,
      active_directives:   [],
    };
  }

  async function setPreference(key, value) {
    return db.preferences.put({ key, value });
  }

  async function counts() {
    const [s, i, n] = await Promise.all([
      db.interactions.where({ type: "saved" }).count(),
      db.interactions.where({ type: "ignored" }).count(),
      db.interactions.count(),
    ]);
    return { saved: s, ignored: i, interactions: n };
  }

  async function exportPersonalGraph() {
    const tables = ["entities", "edges", "interactions", "directives", "collections", "collectionItems", "notes", "preferences"];
    const out = { exportedAt: now(), version: 1 };
    for (const t of tables) out[t] = await db[t].toArray();
    return out;
  }

  async function clearPersonalGraph() {
    await Promise.all([
      db.entities.clear(), db.edges.clear(), db.interactions.clear(),
      db.directives.clear(), db.collections.clear(), db.collectionItems.clear(),
      db.notes.clear(), db.preferences.clear(),
    ]);
    await getOrCreateUserEntity();
    return true;
  }

  window.PersonalGraph = {
    available: true,
    init,
    getOrCreateUserEntity,
    upsertEntity,
    addEdge,
    recordInteraction,
    savePaper,
    ignorePaper,
    moreLikeThis,
    lessLikeThis,
    getSavedPapers,
    getIgnoredPaperIds,
    getRecentInteractions,
    getTopInterests,
    getPersonalContextForAgent,
    setPreference,
    counts,
    exportPersonalGraph,
    clearPersonalGraph,
  };

  // auto-init
  init();
})();
