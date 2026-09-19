/** Shared, DOM-free review state. Events are append-only and refer to comment record IDs. */
export function framePin(time, fps, duration = Infinity) {
  if (!(Number.isFinite(fps) && fps > 0)) throw new Error('fps must be positive');
  const last = Number.isFinite(duration) ? Math.max(0, Math.ceil(duration * fps - 1e-7) - 1) : Infinity;
  const frame = Math.min(last, Math.max(0, Math.floor((Number(time) || 0) * fps + 1e-6)));
  return { frame, t: frame / fps, fps };
}

export function recordId(record) {
  return String(record.id ?? record._id ?? `legacy:${JSON.stringify([record.data?.version, record.data?.t, record.data?.text, record.createdAt])}`);
}

export function replayReviews(comments = [], events = []) {
  const notes = new Map(comments.map(c => [recordId(c), {
    ...c.data, id: recordId(c), createdAt: c.createdAt || '',
    status: 'open', replies: [], evidence: [], history: [],
  }]));
  const seen = new Set();
  events.map((event, index) => ({event, index})).sort((a, b) =>
    String(a.event.createdAt || '').localeCompare(String(b.event.createdAt || '')) || a.index - b.index
  ).forEach(({event}) => {
    const id = recordId(event);
    if (seen.has(id)) return;
    seen.add(id);
    const data = event.data || {}, note = notes.get(String(data.commentId));
    if (!note) return;
    if (data.kind === 'status' && ['open', 'resolved'].includes(data.status)) note.status = data.status;
    else if (data.kind === 'reply') note.replies.push({...data, id, createdAt: event.createdAt});
    else if (data.kind === 'evidence') note.evidence.push({...data, id, createdAt: event.createdAt});
    else return;
    note.history.push(event);
  });
  return [...notes.values()].sort((a, b) => String(a.version || '').localeCompare(String(b.version || '')) || a.t - b.t);
}

export function revisionExport(data, metadata = {}) {
  return { schemaVersion: 2, exportedAt: new Date().toISOString(), ...metadata,
    comments: data.comments || [], events: data.events || [],
    notes: replayReviews(data.comments, data.events) };
}

export function createLocalStore(storage, key, seed = {}) {
  const load = () => {
    const existing = storage.getItem(key);
    if (existing !== null) {
      const data = JSON.parse(existing);
      if (!Array.isArray(data.comments) || !Array.isArray(data.events)) throw new Error('Saved review data is invalid');
      return data;
    }
    const data = {comments: seed.comments || [], events: seed.events || []};
    storage.setItem(key, JSON.stringify(data));
    return data;
  };
  return {
    async read() { return load(); },
    async append(collection, data, id = globalThis.crypto.randomUUID()) {
      if (!['comments', 'events'].includes(collection)) throw new Error('Unknown review collection');
      const state = load();
      const existing = state[collection].find(r => recordId(r) === id);
      if (existing) return existing;
      const record = {id, createdAt: new Date().toISOString(), data};
      state[collection].push(record);
      storage.setItem(key, JSON.stringify(state));
      return record;
    }
  };
}

export function createRemoteStore(fetcher, base = './.herenow/data/') {
  async function list(collection, optional = false) {
    const records = [], cursors = new Set();
    let cursor = '';
    do {
      const response = await fetcher(`${base}${collection}?limit=200${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}`);
      if (optional && response.status === 404) return [];
      if (!response.ok) throw new Error(`Could not load ${collection} (HTTP ${response.status})`);
      const page = await response.json();
      if (!Array.isArray(page.records)) throw new Error(`Invalid ${collection} response`);
      records.push(...page.records);
      cursor = page.nextCursor || page.pagination?.nextCursor || '';
      if (cursor && cursors.has(cursor)) throw new Error('Review pagination repeated a cursor');
      cursors.add(cursor);
    } while (cursor);
    return records;
  }
  return {
    async read() {
      const [comments, events] = await Promise.all([list('comments'), list('reviewEvents', true)]);
      return {comments, events};
    },
    async append(collection, data, id = globalThis.crypto.randomUUID()) {
      const name = collection === 'comments' ? 'comments' : collection === 'events' ? 'reviewEvents' : null;
      if (!name) throw new Error('Unknown review collection');
      const response = await fetcher(base + name, {method: 'POST',
        headers: {'content-type': 'application/json', 'Idempotency-Key': id}, body: JSON.stringify(data)});
      if (!response.ok) throw new Error(`Could not save review (HTTP ${response.status})`);
      return response.json();
    }
  };
}
