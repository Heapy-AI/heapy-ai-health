# -*- coding: utf-8 -*-
"""7카테고리 규칙 분류기 + 섹션 동의어(기능) 그룹핑 테이블.

카테고리: disease / symptom / test / lifestyle / procedure / environmental / service
- superclass는 약한 힌트로만 사용(신뢰불가). 판단은 섹션 구성 + 제목 패턴 기반.
- 애매(증상/질환 경계, 신호부족)한 문서는 needs_llm=True 로 표시하여 내용 LLM 판정 대상으로 분리.
"""
import re

# ---------- 섹션명 정규화 ----------
def norm_sec(n):
    if not n: return ""
    return n.replace(" ", "").replace("　","").strip()

# ---------- 섹션 기능 그룹(동의어 매핑 테이블) ----------
# 정규화(공백제거)된 섹션명 기준
# 요약문도 질환을 정의/서술하는 도입부이므로 정의성 섹션으로 인정
DEF_SEC   = {"정의","개요","요약문","개요-정의","개요-종류","개요-원인","개요-병태생리","개요-경과및예후","개요정의"}
# 강한 치료 시그니처만 포함(자가관리 등 약한 신호는 제외 -> lifestyle 오탐 방지)
SELFTX_SEC= {"치료","약물치료","비약물치료","치료방법","치료-비약물치료"}
SYMP_SEC  = {"증상","연관증상"}
DIAG_SEC  = {"진단및검사","평가및검사"}
CAUSE_SEC = {"원인","병태생리","발생원/원인","발생원원인","원인및감염경로"}
RELD_SEC  = {"관련질환","동반질환","관련증상및질환"}
COMP_SEC  = {"합병증"}
LIFE_SEC  = {"실천방법","맞춤형실천방법","일반적실천방법","생활습관관리"}
# 시술/치료법 문서 시그니처 섹션
PROC_SEC  = {"치료의적응증","치료관련합병증및부작용","치료후관리","치료관련주의사항","치료관련검사"}
# 행정/서비스 문서 시그니처 섹션
SERV_SEC  = {"목적","대상","세부내용","제공절차"}

def is_exam_sec(n):
    # 검사문서 전용 섹션: '검사'로 시작하되 '진단및검사'는 제외
    return n.startswith("검사") and n != "진단및검사"

# ---------- 제목 패턴 ----------
TEST_TITLE = re.compile(r"(검사|촬영|조영술|내시경|스캔|초음파검사|심전도|투시|섭취율|목덜미투명대측정|선별검사)")
PROC_TITLE = re.compile(r"(수술|이식|투석|마취|절제술|성형술|치환술|삽입술|봉합|시술|소생술|수혈|보철|임플란트|근관치료|레진치료|치석제거|정관수술|포경수술|제왕절개|전환술|불소도포|홈메우기|재활|약물요법|화학요법|방사선치료|호르몬대체요법|항응고요법|항생제|진정법|콘택트렌즈|드림렌즈)")
ENV_TITLE  = re.compile(r"(오염|미세먼지|황사|라돈|수은|납\(|중금속|전자파|소음|다이옥신|석면|폭염|한파|대설|배출물질|화학물질|VOC|오존|연소가스|환경과건강|내분비계장애|전자담배|다중이용시설|건강장해|건강수칙)")
SERV_TITLE = re.compile(r"(건강검진|사전연명|호스피스|장기요양|장기기증|재택의료|방문진료|완화의료)")
LIFE_TITLE = re.compile(r"(운동|음주|흡연|손씻기|영양|식이|이유식|식사|다이어트|카페인|담배|생활습관|신체활동|체중조절|위험음주|건강기능식품|디지털과의존|화장품|염분섭취|탄수화물|알려드리겠습니다)")


def classify(doc):
    """doc: 원본 json dict. return dict(category, confidence, source, needs_llm, signals)."""
    title = doc.get("disease","") or ""
    raw_names = [s.get("name","") for s in doc.get("sections",[])]
    names = [norm_sec(n) for n in raw_names]
    S = set(names)

    n_exam = sum(1 for n in names if is_exam_sec(n))
    n_proc = len(S & PROC_SEC)
    n_life = len(S & LIFE_SEC)
    n_serv = len(S & SERV_SEC)
    has_def  = bool(S & DEF_SEC)
    has_tx   = bool(S & SELFTX_SEC)
    has_symp = bool(S & SYMP_SEC)
    has_diag = bool(S & DIAG_SEC)
    has_reld = bool(S & RELD_SEC)
    has_comp = bool(S & COMP_SEC)
    env_content = (("발생원/원인" in names) or ("발생원원인" in names)) and \
                  (("건강문제" in names) or ("건강문제" in names) or ("건강에미치는영향" in names))

    signals = dict(n_exam=n_exam, n_proc=n_proc, n_life=n_life, n_serv=n_serv,
                   has_def=has_def, has_tx=has_tx, has_symp=has_symp,
                   has_diag=has_diag, has_reld=has_reld, has_comp=has_comp)

    cat=None; conf="high"; src=""; needs_llm=False
    clinical = has_symp and has_diag   # 증상+진단 동시 존재 = 임상 질환 문서 구조

    # 1) procedure (시술·치료법): 증상섹션 있으면 질환 문서이므로 제외
    if (n_proc>=1 or PROC_TITLE.search(title)) and not (clinical and n_proc==0):
        cat="procedure"
        if n_proc>=2 or (PROC_TITLE.search(title) and n_proc>=1): src="rule:치료법섹션+시술제목"; conf="high"
        elif n_proc>=1: src="rule:치료법섹션"; conf="high"
        else: src="rule:시술제목"; conf="medium"
    # 2) test (검사방법)
    elif n_exam>=2 or TEST_TITLE.search(title):
        cat="test"
        if n_exam>=2 and TEST_TITLE.search(title): src="rule:검사섹션+검사제목"; conf="high"
        elif n_exam>=2: src="rule:검사섹션우세"; conf="high"
        else: src="rule:검사제목"; conf="medium"
    # 3) service (행정·제도)
    elif SERV_TITLE.search(title) or n_serv>=3:
        cat="service"
        src="rule:서비스제목" if SERV_TITLE.search(title) else "rule:목적+대상+제공절차"
        conf="high"
    # 4) environmental (환경보건)
    elif ENV_TITLE.search(title) or env_content:
        cat="environmental"
        if ENV_TITLE.search(title): src="rule:환경유해물질제목"; conf="high"
        else: src="rule:발생원+건강문제내용"; conf="medium"
    # 5) disease (정의+자기치료) -- lifestyle 보다 먼저: 치료 섹션 있으면 질환
    elif has_def and has_tx:
        cat="disease"; src="rule:정의+자기치료"; conf="high"
    # 6) lifestyle (생활습관관리) -- 임상 질환 구조(증상+진단)가 아닐 때만
    elif (n_life>=1 or LIFE_TITLE.search(title)) and not clinical:
        cat="lifestyle"
        if n_life>=2 or (LIFE_TITLE.search(title) and n_life>=1): src="rule:실천섹션+생활제목"; conf="high"
        elif n_life>=1: src="rule:실천섹션"; conf="high"
        else: src="rule:생활습관제목"; conf="medium"
    # 7) 경계: 증상 위임 vs 정의만-질환  -> LLM 판정 대상
    elif has_symp and has_reld and not has_tx:
        cat="symptom"; src="rule:증상+관련질환위임(치료없음)"; conf="low"; needs_llm=True
    elif (has_symp or has_diag or has_def) and not has_tx:
        # 치료 섹션이 없는 질환/증상 후보 -> 내용 판정 필요
        cat="disease"; src="rule잠정:정의/증상有 치료無"; conf="low"; needs_llm=True
    else:
        cat="unknown"; src="rule:신호부족"; conf="low"; needs_llm=True

    return dict(category=cat, category_confidence=conf, category_source=src,
                needs_llm=needs_llm, signals=signals)
