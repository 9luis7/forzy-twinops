-- Apply after 003 and 004, only to the dedicated demo database.
-- FastAPI's PostgreSQL owner remains the backend access path. Supabase's
-- public Data API roles must not bypass session tokens or expose the corpus.
-- Do not FORCE RLS: the owning backend role must keep its normal access.
DO $demo_private_access$
DECLARE
    target_table TEXT;
    api_role TEXT;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'demo_datasets', 'demo_runs', 'demo_commands', 'demo_events',
        'rag_corpora', 'rag_documents', 'rag_chunks', 'rag_active_corpus'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target_table);
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', target_table);
        FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = api_role) THEN
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I',
                    target_table, api_role
                );
            END IF;
        END LOOP;
    END LOOP;
END
$demo_private_access$;
