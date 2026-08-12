-- Supabase 의료용어 사전의 공개 읽기와 일괄 검색 RPC 연결
-- 작성자: 김진우

ALTER FUNCTION public.normalize_medical_search_text(text)
    SET search_path = public, pg_catalog;
ALTER FUNCTION public.normalize_medical_initials(text)
    SET search_path = public, pg_catalog;
ALTER FUNCTION public.is_medical_initial_input(text)
    SET search_path = public, pg_catalog;
ALTER FUNCTION public.medical_initial_substrings(text)
    SET search_path = public, pg_catalog;
ALTER FUNCTION public.refresh_medical_term_alias_initials()
    SET search_path = public, pg_catalog;
ALTER FUNCTION public.search_medical_terms(text, integer)
    SET search_path = public, pg_catalog;

REVOKE ALL ON public.medical_term, public.medical_term_alias,
    public.medical_term_alias_initial FROM anon, authenticated;
GRANT SELECT ON public.medical_term, public.medical_term_alias,
    public.medical_term_alias_initial TO anon, authenticated;

DROP POLICY IF EXISTS medical_term_read_active ON public.medical_term;
CREATE POLICY medical_term_read_active
    ON public.medical_term
    FOR SELECT
    TO anon, authenticated
    USING (is_active = true);

DROP POLICY IF EXISTS medical_term_alias_read_active ON public.medical_term_alias;
CREATE POLICY medical_term_alias_read_active
    ON public.medical_term_alias
    FOR SELECT
    TO anon, authenticated
    USING (
        is_active = true
        AND EXISTS (
            SELECT 1
            FROM public.medical_term AS term
            WHERE term.canonical_key = medical_term_alias.canonical_key
              AND term.is_active = true
        )
    );

DROP POLICY IF EXISTS medical_term_alias_initial_read_active
    ON public.medical_term_alias_initial;
CREATE POLICY medical_term_alias_initial_read_active
    ON public.medical_term_alias_initial
    FOR SELECT
    TO anon, authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.medical_term_alias AS alias
            JOIN public.medical_term AS term
              ON term.canonical_key = alias.canonical_key
            WHERE alias.alias_id = medical_term_alias_initial.alias_id
              AND alias.is_active = true
              AND term.is_active = true
        )
    );

CREATE OR REPLACE FUNCTION public.search_medical_terms_batch(
    p_queries text[],
    p_limit integer DEFAULT 5
)
RETURNS TABLE (
    input_query text,
    canonical_key varchar,
    canonical_name varchar,
    term_type varchar,
    matched_alias varchar,
    match_score double precision,
    match_kind text,
    match_priority smallint
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_catalog
AS $$
    SELECT
        query.input_query,
        match.canonical_key,
        match.canonical_name,
        match.term_type,
        match.matched_alias,
        match.match_score,
        match.match_kind,
        match.match_priority
    FROM unnest(coalesce(p_queries, ARRAY[]::text[])) AS query(input_query)
    CROSS JOIN LATERAL public.search_medical_terms(
        query.input_query,
        greatest(1, least(coalesce(p_limit, 5), 20))
    ) AS match
    WHERE length(public.normalize_medical_search_text(query.input_query)) >= 2;
$$;

REVOKE ALL ON FUNCTION public.search_medical_terms_batch(text[], integer)
    FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_medical_terms_batch(text[], integer)
    TO anon, authenticated, service_role;
