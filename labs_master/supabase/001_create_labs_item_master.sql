-- 건강검진 Labs Item Master MVP (PostgreSQL 15+)
--
-- 이 파일은 빈 데이터베이스에 적용하는 독립 베이스라인이다.
-- 사용자별 실제 수치·검진일·결과지 원문은 기존 Labs Record에 저장한다.
-- 국가검진 상품/기관별 종합검진 상품은 이 MVP의 관리 대상이 아니다.
-- 같은 검사 항목을 한 번만 정의하고, 이름 차이·패널 구성·참고범위만 분리한다.

BEGIN;

CREATE TABLE labs_item_master (
    item_id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_code        VARCHAR(80) NOT NULL UNIQUE,
    item_name_ko     VARCHAR(200) NOT NULL,
    item_type        VARCHAR(20) NOT NULL DEFAULT 'OBSERVATION',
    item_category    VARCHAR(20) NOT NULL,
    specimen_type    VARCHAR(20),
    result_type      VARCHAR(20) NOT NULL,
    standard_unit    VARCHAR(40),
    item_description TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT ck_labs_item_master_code
        CHECK (item_code ~ '^[A-Z][A-Z0-9_]*$'),
    CONSTRAINT ck_labs_item_master_name
        CHECK (btrim(item_name_ko) <> ''),
    CONSTRAINT ck_labs_item_master_type
        CHECK (item_type IN ('OBSERVATION', 'PANEL', 'REPORT', 'QUESTIONNAIRE')),
    CONSTRAINT ck_labs_item_master_category
        CHECK (item_category IN (
            'LAB', 'VITAL', 'IMAGING', 'ENDOSCOPY',
            'FUNCTION', 'QUESTIONNAIRE', 'OTHER'
        )),
    CONSTRAINT ck_labs_item_master_specimen
        CHECK (specimen_type IS NULL OR specimen_type IN (
            'BLOOD', 'URINE', 'STOOL', 'OTHER'
        )),
    CONSTRAINT ck_labs_item_master_result
        CHECK (result_type IN ('NUMBER', 'CODE', 'TEXT', 'MIXED')),
    CONSTRAINT ck_labs_item_master_unit
        CHECK (standard_unit IS NULL OR btrim(standard_unit) <> '')
);

CREATE TABLE labs_item_alias (
    alias_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id          INTEGER NOT NULL,
    alias_name       VARCHAR(200) NOT NULL,
    normalized_alias VARCHAR(200) NOT NULL,
    alias_type       VARCHAR(20) NOT NULL DEFAULT 'SYNONYM',
    institution_name VARCHAR(200),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_labs_item_alias_item
        FOREIGN KEY (item_id)
        REFERENCES labs_item_master (item_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_labs_item_alias_name
        UNIQUE NULLS NOT DISTINCT (normalized_alias, institution_name),
    CONSTRAINT ck_labs_item_alias_name
        CHECK (btrim(alias_name) <> ''),
    CONSTRAINT ck_labs_item_alias_normalized
        CHECK (btrim(normalized_alias) <> ''),
    CONSTRAINT ck_labs_item_alias_type
        CHECK (alias_type IN (
            'STANDARD', 'SYNONYM', 'ABBREVIATION', 'OCR', 'LOCAL_NAME'
        )),
    CONSTRAINT ck_labs_item_alias_institution
        CHECK (institution_name IS NULL OR btrim(institution_name) <> '')
);

CREATE INDEX ix_labs_item_alias_lookup
    ON labs_item_alias (normalized_alias, institution_name)
    WHERE is_active;

CREATE TABLE labs_panel_item (
    panel_item_id    INTEGER NOT NULL,
    included_item_id INTEGER NOT NULL,
    display_order    SMALLINT NOT NULL,
    requirement_type VARCHAR(20) NOT NULL DEFAULT 'REQUIRED',

    CONSTRAINT pk_labs_panel_item
        PRIMARY KEY (panel_item_id, included_item_id),
    CONSTRAINT fk_labs_panel_item_panel
        FOREIGN KEY (panel_item_id)
        REFERENCES labs_item_master (item_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_labs_panel_item_included
        FOREIGN KEY (included_item_id)
        REFERENCES labs_item_master (item_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_labs_panel_item_not_self
        CHECK (panel_item_id <> included_item_id),
    CONSTRAINT ck_labs_panel_item_display_order
        CHECK (display_order > 0),
    CONSTRAINT ck_labs_panel_item_requirement
        CHECK (requirement_type IN ('REQUIRED', 'OPTIONAL', 'CONDITIONAL'))
);

CREATE INDEX ix_labs_panel_item_included
    ON labs_panel_item (included_item_id, panel_item_id);

CREATE TABLE labs_item_reference_range (
    reference_range_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id            INTEGER NOT NULL,
    applies_to_sex     VARCHAR(10) NOT NULL DEFAULT 'ALL',
    age_from           SMALLINT,
    age_to             SMALLINT,
    minimum_value      NUMERIC(16, 4),
    maximum_value      NUMERIC(16, 4),
    reference_text     TEXT,
    institution_name   VARCHAR(200),
    valid_from         DATE,
    valid_to           DATE,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_labs_item_reference_range_item
        FOREIGN KEY (item_id)
        REFERENCES labs_item_master (item_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_labs_item_reference_range
        UNIQUE NULLS NOT DISTINCT (
            item_id, applies_to_sex, age_from, age_to,
            minimum_value, maximum_value, reference_text,
            institution_name, valid_from
        ),
    CONSTRAINT ck_labs_item_reference_range_sex
        CHECK (applies_to_sex IN ('ALL', 'MALE', 'FEMALE')),
    CONSTRAINT ck_labs_item_reference_range_age_from
        CHECK (age_from IS NULL OR age_from BETWEEN 0 AND 150),
    CONSTRAINT ck_labs_item_reference_range_age_to
        CHECK (age_to IS NULL OR age_to BETWEEN 0 AND 150),
    CONSTRAINT ck_labs_item_reference_range_age
        CHECK (age_from IS NULL OR age_to IS NULL OR age_from <= age_to),
    CONSTRAINT ck_labs_item_reference_range_value
        CHECK (
            minimum_value IS NULL
            OR maximum_value IS NULL
            OR minimum_value <= maximum_value
        ),
    CONSTRAINT ck_labs_item_reference_range_not_empty
        CHECK (
            minimum_value IS NOT NULL
            OR maximum_value IS NOT NULL
            OR reference_text IS NOT NULL
        ),
    CONSTRAINT ck_labs_item_reference_range_institution
        CHECK (institution_name IS NULL OR btrim(institution_name) <> ''),
    CONSTRAINT ck_labs_item_reference_range_period
        CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to)
);

CREATE INDEX ix_labs_item_reference_range_lookup
    ON labs_item_reference_range (item_id, applies_to_sex, age_from, age_to)
    WHERE is_active;

COMMENT ON TABLE labs_item_master IS
    '검진 종류와 무관하게 재사용하는 표준 검사 항목 원장. 실제 사용자 결과는 저장하지 않는다.';
COMMENT ON COLUMN labs_item_master.item_id IS
    '다른 Labs 테이블이 참조하는 내부 식별자.';
COMMENT ON COLUMN labs_item_master.item_code IS
    '표시명이 바뀌어도 유지하는 영문 고정 코드.';
COMMENT ON COLUMN labs_item_master.item_name_ko IS
    '서비스와 운영 화면에 표시하는 대표 한글 검사명.';
COMMENT ON COLUMN labs_item_master.item_type IS
    '단일 결과, 검사 패널, 판독 보고서, 설문 중 검사 구조.';
COMMENT ON COLUMN labs_item_master.item_category IS
    '검색과 화면 묶음에 쓰는 큰 분류이며 의학적 판정은 아니다.';
COMMENT ON COLUMN labs_item_master.specimen_type IS
    '검체 종류. 검체가 없는 신체계측·영상검사 등은 NULL.';
COMMENT ON COLUMN labs_item_master.result_type IS
    'Labs Record에 들어올 대표 결과 형태: 수치, 코드, 서술, 혼합.';
COMMENT ON COLUMN labs_item_master.standard_unit IS
    '내부 비교용 대표 단위. 결과지 원문 단위를 덮어쓰지 않는다.';
COMMENT ON COLUMN labs_item_master.item_description IS
    '검사 항목을 식별하기 위한 짧은 설명. 진단·치료 지침은 VDB의 책임.';
COMMENT ON COLUMN labs_item_master.is_active IS
    '신규 결과 매핑에 사용할지 여부. 과거 기록을 위해 행은 삭제하지 않는다.';

COMMENT ON TABLE labs_item_alias IS
    '병원 표기, 약어, OCR 표기를 표준 검사 항목으로 연결하는 이름 사전.';
COMMENT ON COLUMN labs_item_alias.alias_id IS
    '별칭 행의 내부 식별자.';
COMMENT ON COLUMN labs_item_alias.item_id IS
    '별칭이 가리키는 labs_item_master의 항목.';
COMMENT ON COLUMN labs_item_alias.alias_name IS
    '결과지 원문에 나타날 수 있는 이름 또는 약어.';
COMMENT ON COLUMN labs_item_alias.normalized_alias IS
    '공백·기호·대소문자 차이를 제거한 자동 매칭용 검색값.';
COMMENT ON COLUMN labs_item_alias.alias_type IS
    '대표명, 동의어, 약어, OCR 표기, 기관 전용명 중 구분.';
COMMENT ON COLUMN labs_item_alias.institution_name IS
    '특정 기관에서만 쓰는 표기일 때의 기관명. 공통 표기는 NULL.';
COMMENT ON COLUMN labs_item_alias.is_active IS
    '자동 매핑에 현재 사용할지 여부.';

COMMENT ON TABLE labs_panel_item IS
    'CBC·간기능검사처럼 한 패널에 포함되는 표준 항목의 구성표.';
COMMENT ON COLUMN labs_panel_item.panel_item_id IS
    'item_type이 PANEL인 상위 항목.';
COMMENT ON COLUMN labs_panel_item.included_item_id IS
    '패널 안에 포함되는 하위 검사 항목.';
COMMENT ON COLUMN labs_panel_item.display_order IS
    '패널을 표시하거나 읽을 때의 순서. 의료적 우선순위는 아니다.';
COMMENT ON COLUMN labs_panel_item.requirement_type IS
    '패널에서 필수, 선택, 조건부로 포함되는지의 구분.';

COMMENT ON TABLE labs_item_reference_range IS
    '성별·연령·기관별 참고범위 또는 결과지 판정 기준의 출처 있는 원문 표현.';
COMMENT ON COLUMN labs_item_reference_range.reference_range_id IS
    '참고범위 행의 내부 식별자.';
COMMENT ON COLUMN labs_item_reference_range.item_id IS
    '참고범위가 적용되는 표준 검사 항목.';
COMMENT ON COLUMN labs_item_reference_range.applies_to_sex IS
    '참고범위 적용 성별. 공통 기준은 ALL.';
COMMENT ON COLUMN labs_item_reference_range.age_from IS
    '적용 시작 나이. 제한이 없으면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.age_to IS
    '적용 종료 나이. 제한이 없으면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.minimum_value IS
    '수치 참고범위의 하한. 하한이 없거나 정성 결과면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.maximum_value IS
    '수치 참고범위의 상한. 상한이 없거나 정성 결과면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.reference_text IS
    '음성·양성 같은 정성 기준, 경계 포함 여부, 출처 문구를 원문에 가깝게 기록.';
COMMENT ON COLUMN labs_item_reference_range.institution_name IS
    '기준을 제공한 기관·제도명. 결과지 기관 기준을 추가할 때도 사용한다.';
COMMENT ON COLUMN labs_item_reference_range.valid_from IS
    '기준 적용 시작일. 확인할 수 없으면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.valid_to IS
    '기준 적용 종료일. 현재 유효하면 NULL.';
COMMENT ON COLUMN labs_item_reference_range.is_active IS
    '현재 자동 참조에 사용할지 여부.';

COMMIT;
