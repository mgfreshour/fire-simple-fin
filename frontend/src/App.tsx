import { useCallback, useEffect, useRef, useState } from 'react';

const BRIDGE_CREATE_URL = 'https://bridge.simplefin.org/simplefin/create';

function formatLastActivity(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return 'Never';
  }
}

type Connection = { id: string; label: string | null; created_at: string; link_count: number };
type SimpleFINAccount = { id: string; name: string; currency: string; org_name: string | null };
type ClaimResponse = { connection_id: string; accounts: SimpleFINAccount[]; errors: string[] };
type FireflyAccount = { id: number; name: string; type: string };
type Link = {
  id: string;
  connection_id: string;
  simplefin_account_id: string;
  firefly_account_id: number;
  created_at: string;
  last_sync_at?: string | null;
  last_push_at?: string | null;
};

type TransactionState = 'matched' | 'annotated' | 'unmatched' | 'new';
type DisplayTransaction = {
  id: string;
  type: string;
  state: TransactionState;
  description: string;
  date: string;
  amount: string;
  foreign_amount?: string | null;
  foreign_currency_id?: number | null;
  account_id?: number | null;
  account_name?: string | null;
  category_id?: number | null;
  notes?: string | null;
  candidates?: unknown[];
};
type PushResponse = { pushed: number; errors: { index: number; message: string }[] };

type View = 'home' | 'connect' | 'link' | 'sync' | 'settings';

export default function App() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [health, setHealth] = useState<{ status?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>('home');
  const [setupToken, setSetupToken] = useState('');
  const [claimLoading, setClaimLoading] = useState(false);
  const [claimError, setClaimError] = useState<string | null>(null);
  const [claimResult, setClaimResult] = useState<ClaimResponse | null>(null);
  const [fireflyAccounts, setFireflyAccounts] = useState<FireflyAccount[]>([]);
  const [linkLoading, setLinkLoading] = useState<Record<string, boolean>>({});
  const [linkErrors, setLinkErrors] = useState<Record<string, string>>({});
  const [linkedCount, setLinkedCount] = useState(0);
  const [linkedIds, setLinkedIds] = useState<Set<string>>(new Set());
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set());
  const [selectedFirefly, setSelectedFirefly] = useState<Record<string, number>>({});
  const [links, setLinks] = useState<Link[]>([]);
  const [syncAccountId, setSyncAccountId] = useState<number | null>(null);
  const [syncAccountName, setSyncAccountName] = useState<string>('');
  const [syncStartDate, setSyncStartDate] = useState<string>(() => {
    const d = new Date();
    d.setDate(d.getDate() - 60);
    return d.toISOString().slice(0, 10);
  });
  const [syncEndDate, setSyncEndDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [syncLoading, setSyncLoading] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<DisplayTransaction[]>([]);
  const [pushLoading, setPushLoading] = useState(false);
  const [pushProcessed, setPushProcessed] = useState<number | null>(null);
  const [pushResult, setPushResult] = useState<{ pushed: number; errors: { index: number; message: string }[] } | null>(null);
  const [hasSyncedOnce, setHasSyncedOnce] = useState(false);
  const [settingsConnectionAccounts, setSettingsConnectionAccounts] = useState<Record<string, SimpleFINAccount[]>>({});
  const [settingsConnectionErrors, setSettingsConnectionErrors] = useState<Record<string, string>>({});
  const [disconnectConfirm, setDisconnectConfirm] = useState<string | null>(null);
  const [disconnectLoading, setDisconnectLoading] = useState(false);
  const settingsFetchedRef = useRef<Set<string>>(new Set());

  const loadConnections = useCallback(() => {
    fetch('/api/simplefin/connections')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('Failed to load connections'))))
      .then(setConnections)
      .catch(() => setConnections([]));
  }, []);

  const loadLinks = useCallback(() => {
    fetch('/api/simplefin/links')
      .then((r) => (r.ok ? r.json() : []))
      .then(setLinks)
      .catch(() => setLinks([]));
  }, []);

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(e.message));
    loadConnections();
    loadLinks();
  }, [loadConnections, loadLinks]);

  useEffect(() => {
    if (view === 'home' && fireflyAccounts.length === 0 && links.length > 0) {
      fetch('/api/firefly/accounts')
        .then((r) => (r.ok ? r.json() : []))
        .then(setFireflyAccounts)
        .catch(() => setFireflyAccounts([]));
    }
  }, [view, links.length, fireflyAccounts.length]);

  useEffect(() => {
    if (view !== 'settings' || connections.length === 0) return;
    if (fireflyAccounts.length === 0) {
      fetch('/api/firefly/accounts')
        .then((r) => (r.ok ? r.json() : []))
        .then(setFireflyAccounts)
        .catch(() => setFireflyAccounts([]));
    }
    connections.forEach((c) => {
      if (settingsFetchedRef.current.has(c.id)) return;
      settingsFetchedRef.current.add(c.id);
      fetch(`/api/simplefin/connections/${c.id}/accounts`)
        .then(async (r) => {
          const data = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(Array.isArray(data.detail) ? data.detail.join(' ') : data.detail || r.statusText || 'Failed to load accounts');
          return data as SimpleFINAccount[];
        })
        .then((accounts) => setSettingsConnectionAccounts((prev) => ({ ...prev, [c.id]: accounts })))
        .catch((err: Error) => setSettingsConnectionErrors((prev) => ({ ...prev, [c.id]: err.message })));
    });
  }, [view, connections, fireflyAccounts.length]);

  const handleDisconnect = (connectionId: string) => {
    setDisconnectLoading(true);
    fetch(`/api/simplefin/connections/${connectionId}`, { method: 'DELETE' })
      .then((r) => {
        if (!r.ok) throw new Error('Failed to disconnect');
      })
      .then(() => {
        setDisconnectConfirm(null);
        loadConnections();
        loadLinks();
      })
      .catch(() => setDisconnectConfirm(null))
      .finally(() => setDisconnectLoading(false));
  };

  const handleClaimSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const token = setupToken.trim();
    if (!token) {
      setClaimError('Please paste your Setup Token.');
      return;
    }
    setClaimError(null);
    setClaimLoading(true);
    fetch('/api/simplefin/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ setup_token: token }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || r.statusText || 'Claim failed');
        return data as ClaimResponse;
      })
      .then((data) => {
        setClaimResult(data);
        setView('link');
        setSetupToken('');
        loadConnections();
      })
      .catch((err: Error) => {
        setClaimError(err.message || 'Something went wrong.');
      })
      .finally(() => setClaimLoading(false));
  };

  useEffect(() => {
    if (view === 'link' && claimResult && fireflyAccounts.length === 0) {
      fetch('/api/firefly/accounts')
        .then((r) => (r.ok ? r.json() : []))
        .then(setFireflyAccounts)
        .catch(() => setFireflyAccounts([]));
    }
  }, [view, claimResult, fireflyAccounts.length]);

  const handleLink = (connectionId: string, simplefinAccountId: string, fireflyAccountId: number) => {
    setLinkErrors((prev) => ({ ...prev, [simplefinAccountId]: '' }));
    setLinkLoading((prev) => ({ ...prev, [simplefinAccountId]: true }));
    fetch('/api/simplefin/links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        connection_id: connectionId,
        simplefin_account_id: simplefinAccountId,
        firefly_account_id: fireflyAccountId,
      }),
    })
      .then((r) => r.json().then((d) => ({ ok: r.ok, data: d })))
      .then(({ ok, data }) => {
        if (ok) {
          setLinkedCount((c) => c + 1);
          setLinkedIds((prev) => new Set(prev).add(simplefinAccountId));
          loadConnections();
        } else {
          setLinkErrors((prev) => ({ ...prev, [simplefinAccountId]: (data as { detail?: string }).detail || 'Link failed' }));
        }
      })
      .catch(() => setLinkErrors((prev) => ({ ...prev, [simplefinAccountId]: 'Request failed' })))
      .finally(() => setLinkLoading((prev) => ({ ...prev, [simplefinAccountId]: false })));
  };

  const handleSkip = (id: string) => {
    setSkippedIds((prev) => new Set(prev).add(id));
  };

  const openSync = (fireflyAccountId: number, accountName: string) => {
    setSyncAccountId(fireflyAccountId);
    setSyncAccountName(accountName);
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 60);
    setSyncEndDate(end.toISOString().slice(0, 10));
    setSyncStartDate(start.toISOString().slice(0, 10));
    setSyncError(null);
    setTransactions([]);
    setPushResult(null);
    setHasSyncedOnce(false);
    setView('sync');
  };

  const handleSyncFetch = (e: React.FormEvent) => {
    e.preventDefault();
    if (syncAccountId == null) return;
    setSyncError(null);
    setSyncLoading(true);
    fetch('/api/simplefin/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        firefly_account_id: syncAccountId,
        start_date: syncStartDate,
        end_date: syncEndDate,
      }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(Array.isArray(data.detail) ? data.detail.join(' ') : data.detail || r.statusText || 'Sync failed');
        return data as DisplayTransaction[];
      })
      .then((data) => {
        setHasSyncedOnce(true);
        setTransactions(data);
        loadLinks();
      })
      .catch((err: Error) => setSyncError(err.message || 'Sync failed'))
      .finally(() => setSyncLoading(false));
  };

  const updateTransaction = (index: number, updates: Partial<DisplayTransaction>) => {
    setTransactions((prev) =>
      prev.map((t, i) => (i === index ? { ...t, ...updates } : t))
    );
  };

  const pushPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pushPollRef.current) clearInterval(pushPollRef.current);
    };
  }, []);

  const handlePush = () => {
    if (syncAccountId == null || transactions.length === 0) return;
    setPushLoading(true);
    setPushProcessed(null);
    setPushResult(null);
    fetch('/api/simplefin/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        firefly_account_id: syncAccountId,
        transactions,
      }),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error((data as { detail?: string }).detail || 'Push failed');
        if (r.status !== 202) {
          setPushResult(data as PushResponse);
          loadLinks();
          setPushLoading(false);
          return;
        }
        const { job_id } = data as { job_id: string };
        const poll = () => {
          fetch(`/api/simplefin/push/status/${job_id}`)
            .then((res) => res.json())
            .then((statusData: { status: string; processed?: number; pushed?: number; errors?: { index: number; message: string }[]; message?: string }) => {
              if (statusData.status === 'completed') {
                if (pushPollRef.current) clearInterval(pushPollRef.current);
                pushPollRef.current = null;
                setPushProcessed(null);
                setPushResult({ pushed: statusData.pushed ?? 0, errors: statusData.errors ?? [] });
                loadLinks();
                setPushLoading(false);
              } else if (statusData.status === 'failed') {
                if (pushPollRef.current) clearInterval(pushPollRef.current);
                pushPollRef.current = null;
                setPushProcessed(null);
                setPushResult({ pushed: 0, errors: [{ index: -1, message: statusData.message ?? 'Push failed' }] });
                setPushLoading(false);
              } else {
                setPushProcessed(statusData.processed ?? 0);
              }
            })
            .catch(() => {
              if (pushPollRef.current) clearInterval(pushPollRef.current);
              pushPollRef.current = null;
              setPushProcessed(null);
              setPushResult({ pushed: 0, errors: [{ index: -1, message: 'Failed to check push status' }] });
              setPushLoading(false);
            });
        };
        pushPollRef.current = setInterval(poll, 1000);
        poll();
      })
      .catch((err: Error) => {
        setPushProcessed(null);
        setPushResult({ pushed: 0, errors: [{ index: -1, message: err.message }] });
        setPushLoading(false);
      });
  };

  const linkedAccountsWithNames = links.map((link) => {
    const fa = fireflyAccounts.find((a) => a.id === link.firefly_account_id);
    return { ...link, accountName: fa?.name ?? `Account ${link.firefly_account_id}` };
  });

  const syncLink =
    view === 'sync' && syncAccountId != null
      ? links.find((l) => l.firefly_account_id === syncAccountId)
      : undefined;

  const accountsToShow = claimResult?.accounts ?? [];
  const totalLinkedOrSkipped = linkedCount + skippedIds.size;
  const allDone = accountsToShow.length > 0 && totalLinkedOrSkipped >= accountsToShow.length;

  return (
    <main
      style={{
        padding: 'clamp(1rem, 4vw, 2rem)',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        maxWidth: 560,
        margin: '0 auto',
      }}
    >
      <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
        Fire SimpleFIN
      </h1>
      <p style={{ color: '#555', marginBottom: '1.5rem' }}>
        Connect your bank via SimpleFIN and upload transactions to Firefly III.
      </p>
      {health && (
        <p data-testid="health" style={{ fontSize: '0.875rem', color: '#666', marginBottom: '1rem' }}>
          API: {health.status}
        </p>
      )}
      {error && (
        <p style={{ color: 'crimson', marginBottom: '1rem' }}>API check failed: {error}</p>
      )}

      {view === 'home' && (
        <section aria-label="Connections">
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Connections
          </h2>
          {connections.length === 0 ? (
            <p style={{ color: '#666', marginBottom: '1rem' }}>
              No connections yet. Connect with SimpleFIN to get started.
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, marginBottom: '1rem' }}>
              {connections.map((c) => (
                <li
                  key={c.id}
                  style={{
                    padding: '0.75rem',
                    border: '1px solid #e0e0e0',
                    borderRadius: 8,
                    marginBottom: '0.5rem',
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{c.label || 'SimpleFIN connection'}</span>
                  <span style={{ color: '#666', fontSize: '0.875rem', marginLeft: '0.5rem' }}>
                    {c.link_count} linked
                  </span>
                </li>
              ))}
            </ul>
          )}
          {linkedAccountsWithNames.length > 0 && (
            <>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                Import from SimpleFIN
              </h3>
              <ul style={{ listStyle: 'none', padding: 0, marginBottom: '1rem' }}>
                {linkedAccountsWithNames.map((link) => (
                  <li
                    key={link.id}
                    style={{
                      padding: '0.75rem',
                      border: '1px solid #e0e0e0',
                      borderRadius: 8,
                      marginBottom: '0.5rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '0.5rem',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500 }}>{link.accountName}</div>
                      <div style={{ fontSize: '0.8125rem', color: '#666', marginTop: '0.25rem' }}>
                        Last pull: {formatLastActivity(link.last_sync_at)} · Last push: {formatLastActivity(link.last_push_at)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => openSync(link.firefly_account_id, link.accountName)}
                      style={{
                        padding: '0.4rem 0.75rem',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        background: '#1a1a2e',
                        color: '#fff',
                        border: 'none',
                        borderRadius: 6,
                        cursor: 'pointer',
                      }}
                    >
                      Import from SimpleFIN
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => { setView('connect'); setClaimError(null); setClaimResult(null); }}
              style={{
                padding: '0.6rem 1rem',
                fontSize: '0.9375rem',
                fontWeight: 600,
                background: '#1a1a2e',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
              }}
            >
              Connect with SimpleFIN
            </button>
            {connections.length > 0 && (
              <button
                type="button"
                onClick={() => setView('settings')}
                style={{
                  padding: '0.6rem 1rem',
                  fontSize: '0.9375rem',
                  background: 'transparent',
                  color: '#555',
                  border: '1px solid #ccc',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                Manage connections
              </button>
            )}
          </div>
        </section>
      )}

      {view === 'connect' && (
        <section aria-label="Connect with SimpleFIN">
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Connect with SimpleFIN
          </h2>
          <p style={{ color: '#555', marginBottom: '1rem', fontSize: '0.9375rem' }}>
            Create a token at the SimpleFIN Bridge, then paste it below.
          </p>
          <a
            href={BRIDGE_CREATE_URL}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#2563eb', marginBottom: '1rem', display: 'inline-block' }}
          >
            Open SimpleFIN Bridge to create a token →
          </a>
          <form onSubmit={handleClaimSubmit}>
            <label htmlFor="setup-token" style={{ display: 'block', fontWeight: 500, marginBottom: '0.35rem' }}>
              Setup Token
            </label>
            <textarea
              id="setup-token"
              value={setupToken}
              onChange={(e) => setSetupToken(e.target.value)}
              placeholder="Paste the base64 Setup Token here"
              rows={4}
              disabled={claimLoading}
              autoComplete="off"
              style={{
                width: '100%',
                padding: '0.6rem',
                fontSize: '0.875rem',
                border: '1px solid #ccc',
                borderRadius: 8,
                boxSizing: 'border-box',
                resize: 'vertical',
              }}
            />
            {claimError && (
              <p role="alert" style={{ color: 'crimson', fontSize: '0.875rem', marginTop: '0.5rem' }}>
                {claimError}
              </p>
            )}
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              <button
                type="submit"
                disabled={claimLoading || !setupToken.trim()}
                style={{
                  padding: '0.6rem 1rem',
                  fontSize: '0.9375rem',
                  fontWeight: 600,
                  background: claimLoading ? '#999' : '#1a1a2e',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  cursor: claimLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {claimLoading ? 'Connecting…' : 'Connect'}
              </button>
              <button
                type="button"
                onClick={() => setView('home')}
                style={{
                  padding: '0.6rem 1rem',
                  fontSize: '0.9375rem',
                  background: 'transparent',
                  color: '#555',
                  border: '1px solid #ccc',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      )}

      {view === 'link' && claimResult && (
        <section aria-label="Link accounts">
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Link SimpleFIN accounts to Firefly
          </h2>
          {claimResult.errors.length > 0 && (
            <p role="alert" style={{ color: '#b45309', fontSize: '0.875rem', marginBottom: '1rem' }}>
              {claimResult.errors.join(' ')}
            </p>
          )}
          {accountsToShow.length === 0 ? (
            <p style={{ color: '#666', marginBottom: '1rem' }}>
              No accounts returned. You can go back and try again or continue to home.
            </p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, marginBottom: '1rem' }}>
              {accountsToShow.map((acc) => {
                const skipped = skippedIds.has(acc.id);
                const linkErr = linkErrors[acc.id];
                const loading = linkLoading[acc.id];
                return (
                  <li
                    key={acc.id}
                    style={{
                      padding: '1rem',
                      border: '1px solid #e0e0e0',
                      borderRadius: 8,
                      marginBottom: '0.75rem',
                    }}
                  >
                    <div style={{ fontWeight: 500, marginBottom: '0.35rem' }}>
                      {acc.name || acc.id}
                      {acc.currency && (
                        <span style={{ color: '#666', fontWeight: 400, marginLeft: '0.5rem' }}>
                          {acc.currency}
                        </span>
                      )}
                    </div>
                    {acc.org_name && (
                      <div style={{ fontSize: '0.875rem', color: '#666', marginBottom: '0.5rem' }}>
                        {acc.org_name}
                      </div>
                    )}
                    {skipped ? (
                      <p style={{ fontSize: '0.875rem', color: '#666' }}>Skipped</p>
                    ) : linkedIds.has(acc.id) ? (
                      <p role="status" style={{ fontSize: '0.875rem', color: '#166534', display: 'flex', alignItems: 'center', gap: '0.35rem', fontWeight: 500 }}>
                        <span aria-hidden="true" style={{ fontSize: '1.25rem', lineHeight: 1 }}>✓</span>
                        Linked to {fireflyAccounts.find((fa) => fa.id === selectedFirefly[acc.id])?.name ?? 'Firefly account'}
                      </p>
                    ) : (
                      <>
                        <select
                          id={`firefly-${acc.id}`}
                          value={selectedFirefly[acc.id] ?? ''}
                          onChange={(e) =>
                            setSelectedFirefly((prev) => ({
                              ...prev,
                              [acc.id]: e.target.value ? Number(e.target.value) : 0,
                            }))
                          }
                          disabled={loading}
                          aria-label={`Firefly account for ${acc.name || acc.id}`}
                          style={{
                            width: '100%',
                            padding: '0.5rem',
                            marginBottom: '0.5rem',
                            fontSize: '0.9375rem',
                            border: '1px solid #ccc',
                            borderRadius: 6,
                          }}
                        >
                          <option value="">Choose a Firefly account…</option>
                          {fireflyAccounts.map((fa) => (
                            <option key={fa.id} value={fa.id}>
                              {fa.name} ({fa.type})
                            </option>
                          ))}
                        </select>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <button
                            type="button"
                            disabled={loading || fireflyAccounts.length === 0 || !selectedFirefly[acc.id]}
                            onClick={() => {
                              const val = selectedFirefly[acc.id];
                              if (val) handleLink(claimResult.connection_id, acc.id, val);
                            }}
                            style={{
                              padding: '0.4rem 0.75rem',
                              fontSize: '0.875rem',
                              fontWeight: 600,
                              background: loading ? '#999' : '#1a1a2e',
                              color: '#fff',
                              border: 'none',
                              borderRadius: 6,
                              cursor: loading ? 'not-allowed' : 'pointer',
                            }}
                          >
                            {loading ? 'Linking…' : 'Link'}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSkip(acc.id)}
                            style={{
                              padding: '0.4rem 0.75rem',
                              fontSize: '0.875rem',
                              background: 'transparent',
                              color: '#555',
                              border: '1px solid #ccc',
                              borderRadius: 6,
                              cursor: 'pointer',
                            }}
                          >
                            Skip
                          </button>
                        </div>
                        {linkErr && (
                          <p role="alert" style={{ color: 'crimson', fontSize: '0.8125rem', marginTop: '0.35rem' }}>
                            {linkErr}
                          </p>
                        )}
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {allDone && (
            <p style={{ fontWeight: 500, marginBottom: '1rem' }}>
              Connected; {linkedCount} account{linkedCount !== 1 ? 's' : ''} linked.
              You can import transactions from SimpleFIN next or manage connections from home.
            </p>
          )}
          <button
            type="button"
            onClick={() => { setView('home'); setClaimResult(null); setLinkedCount(0); setLinkedIds(new Set()); setSkippedIds(new Set()); setLinkErrors({}); }}
            style={{
              padding: '0.6rem 1rem',
              fontSize: '0.9375rem',
              fontWeight: 600,
              background: '#1a1a2e',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
            }}
          >
            Back to connections
          </button>
        </section>
      )}

      {view === 'sync' && syncAccountId != null && (
        <section aria-label="Import from SimpleFIN">
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Import from SimpleFIN — {syncAccountName}
          </h2>
          {syncLink ? (
            <p style={{ fontSize: '0.875rem', color: '#666', marginBottom: '1rem' }}>
              Last pull: {formatLastActivity(syncLink.last_sync_at)} · Last push: {formatLastActivity(syncLink.last_push_at)}
            </p>
          ) : null}
          <form onSubmit={handleSyncFetch} style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end', marginBottom: '0.75rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="sr-only">Start date</span>
                <span style={{ fontSize: '0.875rem', color: '#555' }}>From</span>
                <input
                  type="date"
                  value={syncStartDate}
                  onChange={(e) => setSyncStartDate(e.target.value)}
                  disabled={syncLoading}
                  aria-label="Start date"
                  style={{ padding: '0.5rem', fontSize: '0.9375rem', border: '1px solid #ccc', borderRadius: 6 }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="sr-only">End date</span>
                <span style={{ fontSize: '0.875rem', color: '#555' }}>To</span>
                <input
                  type="date"
                  value={syncEndDate}
                  onChange={(e) => setSyncEndDate(e.target.value)}
                  disabled={syncLoading}
                  aria-label="End date"
                  style={{ padding: '0.5rem', fontSize: '0.9375rem', border: '1px solid #ccc', borderRadius: 6 }}
                />
              </label>
              <button
                type="submit"
                disabled={syncLoading}
                style={{
                  padding: '0.5rem 1rem',
                  fontSize: '0.9375rem',
                  fontWeight: 600,
                  background: syncLoading ? '#999' : '#1a1a2e',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  cursor: syncLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {syncLoading ? 'Fetching…' : 'Fetch transactions'}
              </button>
            </div>
            {syncError && (
              <p role="alert" style={{ color: 'crimson', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                {syncError}
              </p>
            )}
          </form>
          {transactions.length === 0 && !syncLoading && !syncError && !hasSyncedOnce && (
            <>
              <p style={{ color: '#666', marginBottom: '1rem' }}>
                Choose a date range and click Fetch transactions to load SimpleFIN data.
              </p>
              <p style={{ color: '#888', fontSize: '0.8125rem', marginBottom: '1rem' }}>
                Sync fetches up to 60 days of data per request. Avoid repeated syncs in one day to stay within provider limits.
              </p>
            </>
          )}
          {hasSyncedOnce && transactions.length === 0 && !syncLoading && (
            <p style={{ color: '#666', fontSize: '0.875rem' }}>No transactions in this range from SimpleFIN.</p>
          )}
          {transactions.length > 0 && (
            <>
              <p style={{ fontSize: '0.875rem', color: '#555', marginBottom: '0.5rem' }}>
                {transactions.length} transaction{transactions.length !== 1 ? 's' : ''}. Edit payee or notes if needed, then push to Firefly.
              </p>
              <ul style={{ listStyle: 'none', padding: 0, marginBottom: '1rem', maxHeight: '50vh', overflow: 'auto' }}>
                {transactions
                  .map((t, i) => ({ t, i }))
                  .sort((a, b) => new Date(b.t.date).getTime() - new Date(a.t.date).getTime())
                  .map(({ t, i }) => {
                    const stateLabel = t.state.charAt(0).toUpperCase() + t.state.slice(1);
                    const stateColor = t.state === 'new' ? '#166534' : t.state === 'matched' ? '#1e40af' : t.state === 'annotated' ? '#92400e' : '#6b7280';
                    return (
                      <li
                        key={`${t.id}-${t.date}-${i}`}
                        style={{
                          padding: '0.75rem',
                          border: '1px solid #e5e7eb',
                          borderRadius: 8,
                          marginBottom: '0.5rem',
                          background: '#fafafa',
                        }}
                      >
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.35rem' }}>
                          <span
                            style={{
                              fontSize: '0.75rem',
                              fontWeight: 600,
                              color: stateColor,
                              background: `${stateColor}22`,
                              padding: '0.2rem 0.5rem',
                              borderRadius: 4,
                            }}
                          >
                            {stateLabel}
                          </span>
                          <span style={{ fontSize: '0.875rem', color: '#555' }}>
                            {new Date(t.date).toLocaleDateString()}
                          </span>
                          <span style={{ fontWeight: 600 }}>{t.amount}</span>
                        </div>
                        <div style={{ marginBottom: '0.35rem' }}>
                          <label className="sr-only" htmlFor={`desc-${i}`}>Payee / description</label>
                          <input
                            id={`desc-${i}`}
                            type="text"
                            value={t.description}
                            onChange={(e) => updateTransaction(i, { description: e.target.value })}
                            style={{
                              width: '100%',
                              padding: '0.4rem',
                              fontSize: '0.9375rem',
                              border: '1px solid #ccc',
                              borderRadius: 6,
                            }}
                          />
                        </div>
                        <div>
                          <label className="sr-only" htmlFor={`notes-${i}`}>Notes</label>
                          <input
                            id={`notes-${i}`}
                            type="text"
                            value={t.notes ?? ''}
                            onChange={(e) => updateTransaction(i, { notes: e.target.value || null })}
                            placeholder="Notes"
                            style={{
                              width: '100%',
                              padding: '0.4rem',
                              fontSize: '0.875rem',
                              border: '1px solid #ccc',
                              borderRadius: 6,
                            }}
                          />
                        </div>
                      </li>
                    );
                  })}
              </ul>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={handlePush}
                  disabled={pushLoading}
                  style={{
                    padding: '0.6rem 1rem',
                    fontSize: '0.9375rem',
                    fontWeight: 600,
                    background: pushLoading ? '#999' : '#1a1a2e',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 8,
                    cursor: pushLoading ? 'not-allowed' : 'pointer',
                  }}
                >
                  {pushLoading ? (pushProcessed != null ? `Pushing… ${pushProcessed}` : 'Pushing…') : 'Push to Firefly'}
                </button>
                {pushResult != null && (
                  <span role="status" style={{ fontSize: '0.875rem', color: pushResult.errors.length > 0 ? '#b45309' : '#166534' }}>
                    {pushResult.pushed} imported.
                    {pushResult.errors.length > 0 && ` ${pushResult.errors.length} failed.`}
                  </span>
                )}
              </div>
              {pushResult != null && pushResult.errors.length > 0 && (
                <ul style={{ marginTop: '0.5rem', paddingLeft: '1.25rem', fontSize: '0.875rem', color: '#b45309' }}>
                  {pushResult.errors.map((err) => (
                    <li key={err.index}>
                      Transaction {err.index + 1}: {err.message}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          <button
            type="button"
            onClick={() => { setView('home'); setSyncAccountId(null); setTransactions([]); setPushResult(null); }}
            style={{
              marginTop: '1rem',
              padding: '0.6rem 1rem',
              fontSize: '0.9375rem',
              background: 'transparent',
              color: '#555',
              border: '1px solid #ccc',
              borderRadius: 8,
              cursor: 'pointer',
            }}
          >
            Back to connections
          </button>
        </section>
      )}

      {view === 'settings' && (
        <section aria-label="Manage SimpleFIN connections">
          <h2 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Connections
          </h2>
          <p style={{ color: '#555', fontSize: '0.9375rem', marginBottom: '1rem' }}>
            View linked accounts and disconnect if needed. To use a new Setup Token, use Connect with SimpleFIN and paste a new token; you can disconnect this connection first if you prefer.
          </p>
          {connections.length === 0 ? (
            <p style={{ color: '#666', marginBottom: '1rem' }}>No connections. Connect with SimpleFIN from the home page.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, marginBottom: '1rem' }}>
              {connections.map((c) => {
                const connLinks = links.filter((l) => l.connection_id === c.id);
                const accounts = settingsConnectionAccounts[c.id];
                const connError = settingsConnectionErrors[c.id];
                return (
                  <li
                    key={c.id}
                    style={{
                      padding: '1rem',
                      border: '1px solid #e0e0e0',
                      borderRadius: 8,
                      marginBottom: '0.75rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <span style={{ fontWeight: 600 }}>{c.label || 'SimpleFIN connection'}</span>
                      <span style={{ fontSize: '0.875rem', color: '#666' }}>{c.link_count} linked</span>
                    </div>
                    {connError && (
                      <p role="alert" style={{ color: '#b45309', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                        {connError}
                        {connError.toLowerCase().includes('disabled') || connError.toLowerCase().includes('403') ? ' Create a new token at the Bridge and reconnect, or disconnect this connection.' : ''}
                      </p>
                    )}
                    {!connError && accounts && connLinks.length > 0 && (
                      <ul style={{ listStyle: 'none', padding: 0, marginBottom: '0.75rem', fontSize: '0.875rem' }}>
                        {connLinks.map((link) => {
                          const sfinName = accounts.find((a) => a.id === link.simplefin_account_id)?.name || link.simplefin_account_id;
                          const ffName = fireflyAccounts.find((a) => a.id === link.firefly_account_id)?.name ?? `Account ${link.firefly_account_id}`;
                          return (
                            <li key={link.id} style={{ color: '#555', marginBottom: '0.25rem' }}>
                              {sfinName} → {ffName}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                    {disconnectConfirm === c.id ? (
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.875rem', marginRight: '0.5rem' }}>Disconnect? All links will be removed.</span>
                        <button
                          type="button"
                          disabled={disconnectLoading}
                          onClick={() => handleDisconnect(c.id)}
                          style={{
                            padding: '0.4rem 0.75rem',
                            fontSize: '0.875rem',
                            fontWeight: 600,
                            background: disconnectLoading ? '#999' : '#b91c1c',
                            color: '#fff',
                            border: 'none',
                            borderRadius: 6,
                            cursor: disconnectLoading ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {disconnectLoading ? 'Disconnecting…' : 'Yes, disconnect'}
                        </button>
                        <button
                          type="button"
                          disabled={disconnectLoading}
                          onClick={() => setDisconnectConfirm(null)}
                          style={{
                            padding: '0.4rem 0.75rem',
                            fontSize: '0.875rem',
                            background: 'transparent',
                            color: '#555',
                            border: '1px solid #ccc',
                            borderRadius: 6,
                            cursor: 'pointer',
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setDisconnectConfirm(c.id)}
                        style={{
                          padding: '0.4rem 0.75rem',
                          fontSize: '0.875rem',
                          background: 'transparent',
                          color: '#b91c1c',
                          border: '1px solid #b91c1c',
                          borderRadius: 6,
                          cursor: 'pointer',
                        }}
                      >
                        Disconnect
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          <button
            type="button"
            onClick={() => {
              setView('home');
              setSettingsConnectionAccounts({});
              setSettingsConnectionErrors({});
              settingsFetchedRef.current = new Set();
            }}
            style={{
              padding: '0.6rem 1rem',
              fontSize: '0.9375rem',
              background: 'transparent',
              color: '#555',
              border: '1px solid #ccc',
              borderRadius: 8,
              cursor: 'pointer',
            }}
          >
            Back to home
          </button>
        </section>
      )}
    </main>
  );
}
