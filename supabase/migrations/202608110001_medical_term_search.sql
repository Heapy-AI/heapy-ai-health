-- 질문 정규화용 표준 의료용어 사전.
--
-- 원문 청크/벡터와 표준용어를 분리한다. 검색 전 단계에서는 이 테이블의
-- canonical_key를 기준으로 질문을 재작성하고, 답변은 기존 지식 청크에서만
-- 생성한다. 따라서 오타 보정이 의료적 판단이나 진단을 대신하지 않는다.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE OR REPLACE FUNCTION normalize_medical_search_text(value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT regexp_replace(
        lower(coalesce(value, '')),
        '[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]+',
        '',
        'g'
    )
$$;

CREATE OR REPLACE FUNCTION normalize_medical_initials(value TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    current_character TEXT;
    codepoint INTEGER;
    initial_index INTEGER;
    result TEXT := '';
BEGIN
    FOR current_character IN
        SELECT regexp_split_to_table(lower(coalesce(value, '')), '')
    LOOP
        IF current_character ~ '^[ㄱ-ㅎ]$' THEN
            result := result || current_character;
            CONTINUE;
        END IF;

        codepoint := ascii(current_character);
        IF codepoint BETWEEN 44032 AND 55203 THEN
            initial_index := floor((codepoint - 44032) / 588);
            result := result || substr(
                'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ',
                initial_index + 1,
                1
            );
        END IF;
    END LOOP;
    RETURN translate(result, 'ㄲㄸㅃㅆㅉ', 'ㄱㄷㅂㅅㅈ');
END;
$$;

-- 실제 초성 자모만 입력된 경우에만 초성 검색을 활성화한다.
-- "하이"도 초성열로 계산하면 "혈압"의 부분열 "ㅎㅇ"와 충돌하므로,
-- 일반 한글 음절은 trigram/Levenshtein 계열 오타 검색으로만 평가한다.
CREATE OR REPLACE FUNCTION is_medical_initial_input(value TEXT)
RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
AS $$
    WITH normalized AS (
        SELECT normalize_medical_search_text(value) AS query_key
    )
    SELECT query_key <> ''
       AND query_key ~ '^[ㄱ-ㅎ]+$'
    FROM normalized;
$$;

CREATE TABLE IF NOT EXISTS medical_term (
    canonical_key  VARCHAR(160) PRIMARY KEY,
    canonical_name VARCHAR(200) NOT NULL,
    term_type      VARCHAR(30) NOT NULL
        CHECK (term_type IN ('MEDICATION', 'DISEASE', 'SYMPTOM', 'SCREENING', 'INGREDIENT', 'OTHER')),
    metadata       JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS medical_term_alias (
    alias_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    canonical_key   VARCHAR(160) NOT NULL REFERENCES medical_term(canonical_key) ON DELETE RESTRICT,
    alias_display   VARCHAR(200) NOT NULL,
    alias_normalized TEXT GENERATED ALWAYS AS (normalize_medical_search_text(alias_display)) STORED,
    alias_initials  TEXT GENERATED ALWAYS AS (normalize_medical_initials(alias_display)) STORED,
    alias_type      VARCHAR(30) NOT NULL DEFAULT 'USER_ALIAS'
        CHECK (alias_type IN ('CANONICAL', 'SYNONYM', 'BRAND', 'ABBREVIATION', 'USER_ALIAS')),
    priority        SMALLINT NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT medical_term_alias_nonempty CHECK (length(trim(alias_display)) >= 2),
    CONSTRAINT medical_term_alias_normalized_nonempty CHECK (length(alias_normalized) >= 2),
    CONSTRAINT uq_medical_term_alias UNIQUE (canonical_key, alias_normalized)
);

CREATE INDEX IF NOT EXISTS idx_medical_term_type_active
    ON medical_term (term_type, is_active);

CREATE INDEX IF NOT EXISTS idx_medical_term_alias_lookup
    ON medical_term_alias USING GIN (alias_normalized gin_trgm_ops)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_medical_term_alias_canonical
    ON medical_term_alias (canonical_key, priority DESC);

-- 기존에 이 migration을 먼저 적용한 DB에도 초성 검색 열을 보강한다.
ALTER TABLE medical_term_alias
    ADD COLUMN IF NOT EXISTS alias_initials
    TEXT GENERATED ALWAYS AS (normalize_medical_initials(alias_display)) STORED;

CREATE INDEX IF NOT EXISTS idx_medical_term_alias_initials
    ON medical_term_alias (alias_initials)
    WHERE is_active = TRUE;

-- 전체 alias의 한글 연속 구간에서 초성 부분열을 자동으로 만든다.
-- 예: 고혈압 -> ㄱㅎ, ㄱㅎㅇ, ㅎㅇ / 표면형: 고혈, 고혈압, 혈압
CREATE OR REPLACE FUNCTION medical_initial_substrings(value TEXT)
RETURNS TABLE (initial_key TEXT, surface_display TEXT)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    current_character TEXT;
    current_initial TEXT;
    codepoint INTEGER;
    run_surface TEXT := '';
    run_initials TEXT := '';
    run_length INTEGER;
    start_index INTEGER;
    end_index INTEGER;
BEGIN
    FOR current_character IN
        SELECT regexp_split_to_table(lower(coalesce(value, '')), '')
    LOOP
        codepoint := ascii(current_character);
        IF current_character ~ '^[ㄱ-ㅎ]$' THEN
            current_initial := translate(current_character, 'ㄲㄸㅃㅆㅉ', 'ㄱㄷㅂㅅㅈ');
        ELSIF codepoint BETWEEN 44032 AND 55203 THEN
            current_initial := translate(
                substr(
                    'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ',
                    floor((codepoint - 44032) / 588)::INTEGER + 1,
                    1
                ),
                'ㄲㄸㅃㅆㅉ',
                'ㄱㄷㅂㅅㅈ'
            );
        ELSE
            run_length := char_length(run_surface);
            IF run_length >= 2 THEN
                FOR start_index IN 1..run_length LOOP
                    FOR end_index IN 1..run_length LOOP
                        IF end_index <= start_index THEN
                            CONTINUE;
                        END IF;
                        initial_key := substr(
                            run_initials,
                            start_index,
                            end_index - start_index + 1
                        );
                        surface_display := substr(
                            run_surface,
                            start_index,
                            end_index - start_index + 1
                        );
                        RETURN NEXT;
                    END LOOP;
                END LOOP;
            END IF;
            run_surface := '';
            run_initials := '';
            CONTINUE;
        END IF;

        run_surface := run_surface || current_character;
        run_initials := run_initials || current_initial;
    END LOOP;

    run_length := char_length(run_surface);
    IF run_length >= 2 THEN
        FOR start_index IN 1..run_length LOOP
            FOR end_index IN 1..run_length LOOP
                IF end_index <= start_index THEN
                    CONTINUE;
                END IF;
                initial_key := substr(
                    run_initials,
                    start_index,
                    end_index - start_index + 1
                );
                surface_display := substr(
                    run_surface,
                    start_index,
                    end_index - start_index + 1
                );
                RETURN NEXT;
            END LOOP;
        END LOOP;
    END IF;
    RETURN;
END;
$$;

CREATE TABLE IF NOT EXISTS medical_term_alias_initial (
    alias_id       BIGINT NOT NULL REFERENCES medical_term_alias(alias_id) ON DELETE CASCADE,
    initial_key    TEXT NOT NULL,
    surface_display TEXT NOT NULL,
    PRIMARY KEY (alias_id, initial_key, surface_display)
);

CREATE INDEX IF NOT EXISTS idx_medical_term_alias_initial_key
    ON medical_term_alias_initial (initial_key, alias_id);

CREATE OR REPLACE FUNCTION refresh_medical_term_alias_initials()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM medical_term_alias_initial
    WHERE alias_id = NEW.alias_id;

    IF NEW.is_active THEN
        INSERT INTO medical_term_alias_initial
            (alias_id, initial_key, surface_display)
        SELECT
            NEW.alias_id,
            forms.initial_key,
            forms.surface_display
        FROM medical_initial_substrings(NEW.alias_display) AS forms
        ON CONFLICT DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_medical_term_alias_initials
    ON medical_term_alias;

CREATE TRIGGER trg_medical_term_alias_initials
AFTER INSERT OR UPDATE OF alias_display, is_active
ON medical_term_alias
FOR EACH ROW
EXECUTE FUNCTION refresh_medical_term_alias_initials();

INSERT INTO medical_term_alias_initial
    (alias_id, initial_key, surface_display)
SELECT
    ma.alias_id,
    forms.initial_key,
    forms.surface_display
FROM medical_term_alias AS ma
CROSS JOIN LATERAL medical_initial_substrings(ma.alias_display) AS forms
WHERE ma.is_active = TRUE
ON CONFLICT DO NOTHING;

-- 반환 컬럼에 match_priority를 추가하므로 기존 함수의 반환 타입을
-- 안전하게 교체한다.
DROP FUNCTION IF EXISTS search_medical_terms(TEXT, INTEGER);

CREATE OR REPLACE FUNCTION search_medical_terms(
    p_query TEXT,
    p_limit INTEGER DEFAULT 8
)
RETURNS TABLE (
    canonical_key   VARCHAR,
    canonical_name  VARCHAR,
    term_type       VARCHAR,
    matched_alias   VARCHAR,
    match_score     DOUBLE PRECISION,
    match_kind      TEXT,
    match_priority  SMALLINT
)
LANGUAGE SQL
STABLE
AS $$
    WITH input AS (
        SELECT
            normalize_medical_search_text(p_query) AS query_key,
            normalize_medical_initials(p_query) AS query_initials,
            is_medical_initial_input(p_query) AS query_is_initial_input
    ), ranked AS (
        SELECT
            mt.canonical_key,
            mt.canonical_name,
            mt.term_type,
            ma.alias_display AS matched_alias,
            CASE
                WHEN ma.alias_normalized = input.query_key THEN 1.0::DOUBLE PRECISION
                WHEN position(ma.alias_normalized in input.query_key) > 0
                  OR position(input.query_key in ma.alias_normalized) > 0
                    THEN 0.96::DOUBLE PRECISION
                WHEN ma.alias_initials <> ''
                 AND ma.alias_initials = input.query_initials
                 AND input.query_is_initial_input
                    THEN 0.92::DOUBLE PRECISION
                ELSE GREATEST(
                    similarity(ma.alias_normalized, input.query_key),
                    word_similarity(ma.alias_normalized, input.query_key),
                    CASE
                        WHEN length(ma.alias_normalized) <= 255
                         AND length(input.query_key) <= 255
                            THEN 1.0 - (
                                levenshtein(ma.alias_normalized, input.query_key)::DOUBLE PRECISION
                                / GREATEST(length(ma.alias_normalized), length(input.query_key), 1)
                            )
                        ELSE 0.0
                    END
                )
            END AS match_score,
            CASE
                WHEN ma.alias_normalized = input.query_key THEN 'exact'
                WHEN position(ma.alias_normalized in input.query_key) > 0
                  OR position(input.query_key in ma.alias_normalized) > 0 THEN 'substring'
                WHEN ma.alias_initials <> ''
                 AND ma.alias_initials = input.query_initials
                 AND input.query_is_initial_input THEN 'initials'
                ELSE 'fuzzy'
            END AS match_kind,
            ma.priority
        FROM medical_term mt
        JOIN medical_term_alias ma ON ma.canonical_key = mt.canonical_key
        CROSS JOIN input
        WHERE mt.is_active = TRUE
          AND ma.is_active = TRUE
          AND input.query_key <> ''
          AND (
              ma.alias_normalized = input.query_key
              OR ma.alias_normalized % input.query_key
              OR word_similarity(ma.alias_normalized, input.query_key) >= 0.35
              OR position(ma.alias_normalized in input.query_key) > 0
              OR position(input.query_key in ma.alias_normalized) > 0
             OR (
                  input.query_initials <> ''
                  AND input.query_is_initial_input
                  AND ma.alias_initials = input.query_initials
              )
          )
        UNION ALL
        SELECT
            mt.canonical_key,
            mt.canonical_name,
            mt.term_type,
            forms.surface_display::VARCHAR AS matched_alias,
            0.88::DOUBLE PRECISION AS match_score,
            'initials_substring'::TEXT AS match_kind,
            ma.priority
        FROM medical_term mt
        JOIN medical_term_alias ma ON ma.canonical_key = mt.canonical_key
        JOIN medical_term_alias_initial forms ON forms.alias_id = ma.alias_id
        CROSS JOIN input
        WHERE mt.is_active = TRUE
          AND ma.is_active = TRUE
          AND input.query_initials <> ''
          AND input.query_is_initial_input
          AND forms.initial_key = input.query_initials
          AND forms.initial_key <> ma.alias_initials
    ), best_per_canonical AS (
        SELECT DISTINCT ON (canonical_key)
            canonical_key,
            canonical_name,
            term_type,
            matched_alias,
            match_score,
            match_kind,
            priority
        FROM ranked
        ORDER BY canonical_key,
                 match_score DESC,
                 priority DESC,
                 length(normalize_medical_search_text(matched_alias)) DESC,
                 matched_alias
    )
    SELECT
        best_per_canonical.canonical_key,
        best_per_canonical.canonical_name,
        best_per_canonical.term_type,
        best_per_canonical.matched_alias,
        best_per_canonical.match_score,
        best_per_canonical.match_kind,
        best_per_canonical.priority::SMALLINT AS match_priority
    FROM best_per_canonical
    ORDER BY best_per_canonical.match_score DESC,
             best_per_canonical.priority DESC,
             length(normalize_medical_search_text(best_per_canonical.matched_alias)) DESC,
             best_per_canonical.canonical_key
    LIMIT GREATEST(1, LEAST(coalesce(p_limit, 8), 20));
$$;

COMMENT ON FUNCTION search_medical_terms IS
    'RDB 표준 의료용어·별칭·trigram·초성 부분열 오타 후보 검색. 결과 score가 임계값을 넘을 때만 질문을 재작성한다.';
