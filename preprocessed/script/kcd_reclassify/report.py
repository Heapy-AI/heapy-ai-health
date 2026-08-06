# -*- coding: utf-8 -*-
"""Step 5 요약 리포트 + CSV 생성.
- summary_report.md : 카테고리 분포(전/후), 매칭률, 요약
- mismatch_review.csv : 기존 superclass ↔ 새 category 불일치 목록
- unmatched_kcd.csv : KCD 매칭 실패 질환명(문서/임베디드)
- low_confidence.csv : category_confidence=low 문서
"""
import json, os, glob, csv, io, sys
from collections import Counter, defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "output"))
REP = os.path.join(OUT, "_reports")
os.makedirs(REP, exist_ok=True)

# 새 category -> 기대 superclass (불일치 판정용)
CAT2SUPER = {
    "disease":"건강문제", "symptom":"건강문제",
    "lifestyle":"생활습관 관리", "environmental":"생활습관 관리", "service":"생활습관 관리",
    "test":"검사방법", "procedure":"치료방법",
}

def main():
    files = [f for f in glob.glob(os.path.join(OUT, "*.json"))]
    docs=[]
    for f in files:
        d=json.load(open(f, encoding="utf-8"))
        d["_file"]=os.path.basename(f)
        docs.append(d)
    n=len(docs)

    cat_cnt = Counter(d["category"] for d in docs)
    super_cnt = Counter(d.get("superclass","") for d in docs)
    conf_cnt = Counter(d["category_confidence"] for d in docs)
    crosstab = defaultdict(Counter)
    for d in docs:
        crosstab[d["category"]][d.get("superclass","")]+=1

    # ---- mismatch ----
    mism=[]
    for d in docs:
        exp = CAT2SUPER.get(d["category"])
        if exp and exp != d.get("superclass",""):
            mism.append(d)
    with open(os.path.join(REP,"mismatch_review.csv"),"w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["file","disease","old_superclass","new_category","confidence","category_source"])
        for d in sorted(mism,key=lambda x:(x["category"],x["_file"])):
            w.writerow([d["_file"],d.get("disease"),d.get("superclass"),d["category"],d["category_confidence"],d.get("category_source","")])

    # ---- KCD 매칭 통계 ----
    dz=[d for d in docs if d["category"]=="disease"]
    dz_matched=[d for d in dz if d.get("kcd_matches")]
    dz_unmatched=[d for d in dz if not d.get("kcd_matches")]
    # 문서 단위 best match_type
    ORDER=["exact","paren","alias","substring","fuzzy"]
    def best_type(ms):
        ts=[m["match_type"] for m in ms]
        for t in ORDER:
            if t in ts: return t
        return None
    dz_best=Counter(best_type(d["kcd_matches"]) for d in dz_matched)

    # 치료 섹션 없이 disease로 판정된 문서(정의 각주용)
    TX_SEC={"치료","약물치료","비약물치료","치료방법","치료-비약물치료"}
    def sec_names(d):
        return {s.get("name","").replace(" ","") for s in d.get("sections",[])}
    dz_notx=[d for d in docs if d["category"]=="disease" and not (sec_names(d) & TX_SEC)]
    # 반대 방향: 치료 섹션이 있는데도 symptom으로 판정된 문서(치료가 원인질환으로 위임되는 경우)
    sy_tx=[d for d in docs if d["category"]=="symptom" and (sec_names(d) & TX_SEC)]

    # symptom 문서(자체 매칭 대상) + 하위 태그 분포
    sy=[d for d in docs if d["category"]=="symptom"]
    sy_matched=[d for d in sy if d.get("kcd_matches")]
    sy_kind=Counter(d.get("symptom_kind","(없음)") for d in sy)
    sy_lab=[d for d in sy if d.get("symptom_kind")=="lab_finding"]
    # KCD 연결이 전혀 없는 symptom(자체 매칭도, 코드 붙은 임베디드도 없음)
    sy_nolink=[d for d in sy if not d.get("kcd_matches")
               and not any(e.get("kcd_matches") for e in d.get("embedded_disease_chunks",[]))]

    # 임베디드
    emb_all=[];
    for d in docs:
        for e in d.get("embedded_disease_chunks",[]):
            emb_all.append((d,e))
    emb_matched=[e for _,e in emb_all if e.get("kcd_matches")]
    emb_unmatched=[(d,e) for d,e in emb_all if not e.get("kcd_matches")]
    emb_best=Counter(best_type(e["kcd_matches"]) for e in emb_matched)

    # 후보 단위 match_type 분포
    cand_types=Counter()
    for d in dz_matched:
        for m in d["kcd_matches"]: cand_types[m["match_type"]]+=1
    for _,e in emb_all:
        for m in e.get("kcd_matches",[]): cand_types[m["match_type"]]+=1

    # ---- unmatched CSV ----
    with open(os.path.join(REP,"unmatched_kcd.csv"),"w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["type","file","name","category/section"])
        for d in sorted(dz_unmatched,key=lambda x:x["_file"]):
            w.writerow(["disease문서",d["_file"],d.get("disease"),d["category"]])
        for d,e in emb_unmatched:
            w.writerow(["임베디드",d["_file"],e["chunk_name"],e.get("section_source","")])

    # ---- low confidence CSV ----
    low=[d for d in docs if d["category_confidence"]=="low"]
    with open(os.path.join(REP,"low_confidence.csv"),"w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["file","disease","new_category","old_superclass","category_source"])
        for d in sorted(low,key=lambda x:x["_file"]):
            w.writerow([d["_file"],d.get("disease"),d["category"],d.get("superclass"),d.get("category_source","")])

    # 중복 섹션 제거된 문서
    dedup=[d for d in docs if d.get("dedup_removed_sections",0)>0]

    # ---- summary_report.md ----
    L=[]
    L.append("# 질병관리청 건강정보 재분류 + KCD-9 매칭 요약 리포트\n")
    L.append(f"- 총 문서: **{n}건** (경로: preprocessed/disease_info/kdca)\n")
    try:
        kd=json.load(open(os.path.join(os.path.dirname(__file__),"kcd_dict.json"),encoding="utf-8"))["stats"]
        L.append(f"- KCD-9 딕셔너리: 대표어 {kd['headwords']:,} + 이명 {kd['aliases']:,} (고유 정규화키 {kd['unique_keys']:,})\n")
    except Exception:
        pass
    L.append("\n## 0. 카테고리 정의\n")
    L.append("7개 카테고리로 재분류함. superclass(기존 라벨)는 신뢰 불가하여 참고용 힌트로만 쓰고, "
             "각 문서의 **섹션 구성 + 내용 의미**로 판정함. 애매한 문서는 섹션 내용을 직접 읽어 판정(category_source가 `llm:`로 시작).\n")
    L.append("| category | 정의 | 대표 판정 근거 | 예시 |")
    L.append("|---|---|---|---|")
    L.append("| **disease** (질환) | 표제어 자체가 확정 진단명인 문서. 치료·관리법이 함께 있으면 전형적이나, 진단명이 분명하면 치료 섹션이 없어도 disease | 정의성 섹션 + 치료 섹션(치료/약물 치료/비약물 치료) 동시 존재. 치료 섹션이 없으면 표제어가 진단명인지 내용으로 판정 | 심부전, 당뇨병, 유선염, 외상성 뇌손상 |")
    L.append("| **symptom** (증상/징후·검사이상소견) | 표제어가 확정 진단명이 아닌 증상·징후 또는 검사 이상소견인 문서. 치료 섹션이 있어도 그 내용이 원인 질환의 치료로 위임되면 symptom | 본문의 자기규정(‘~는 증상’) + 치료의 원인질환 위임. 치료 섹션 부재는 필요조건이 아님 | 두통, 어지럼, 두근거림, 심잡음, 단백뇨 |")
    L.append("| **test** (검사방법) | 표제어가 검사·검진명이거나 섹션이 검사 목적·준비·절차·결과 해석 위주로 구성된 문서 | 검사 전용 섹션(검사 목적/절차/항목/결과 해석 등) 2개 이상, 또는 검사·촬영·내시경·스캔류 제목 | 간기능검사, 대장내시경, 심전도검사, 혈청검사 |")
    L.append("| **procedure** (시술·치료법) | 표제어가 시술·수술·치료법·치료기기명인 문서 | 치료법 전용 섹션(치료의 적응증/치료 후 관리 등), 또는 수술·이식·투석·마취·시술류 제목 | 제왕절개술, 각막이식, 혈액투석, 심장박동조율기 |")
    L.append("| **lifestyle** (생활습관관리) | 특정 진단명이 아니라 실천 수칙·운동·식이·예방·발달지도 등 생활 속 관리·예방 위주의 문서 | 실천 방법/맞춤형 실천 방법/생활습관 관리 섹션, 또는 예방·발달·자가관리 안내(임상 질환 구조 아님) | 음주, 손씻기, 영양제, 예방접종, 정상소아의 성장 |")
    L.append("| **environmental** (환경보건) | 환경 유해물질·기후 요인 등 환경이 건강에 미치는 영향과 대처를 다루는 문서 | 발생원/원인 + 건강문제 섹션 구조, 또는 오염·미세먼지·중금속·전자파류 제목 | 황사와 미세먼지, 생활 속의 라돈, 수질오염 |")
    L.append("| **service** (행정·제도) | 진단·치료가 아니라 보건의료 제도·서비스·절차를 안내하는 문서 | 목적/대상/세부 내용/제공 절차 섹션, 또는 건강검진·연명의료·장기이식류 제목 | 국가건강검진, 사전연명의료결정, 호스피스 완화의료 |")
    L.append(f"\n> **disease/symptom 경계**: 치료 섹션 유무는 결정 기준이 아니다. 판정은 표제어가 확정 진단명인지, "
             f"그리고 치료 내용이 그 자체를 겨냥하는지 원인 질환으로 위임되는지로 한다. "
             f"현재 치료 섹션 없이 disease로 둔 문서 **{len(dz_notx)}건**(진단명이 분명한 경우: 외상성 뇌손상, 자연유산, 열상 등), "
             f"치료 섹션이 있으면서 symptom으로 둔 문서 **{len(sy_tx)}건**(치료가 원인 질환으로 위임되는 경우: 두근거림, 두통 등)\n")
    L.append("\n> **KCD-9 매칭 대상**: `disease` 문서 + `symptom` 문서 + `symptom`/`test` 문서에서 추출한 임베디드 질환. "
             "(KCD R00-R99가 증상·징후 및 검사 이상소견 전용 章이므로 symptom 문서의 자체 매칭도 유효함. "
             "검사·시술·생활습관·환경·행정 문서는 진단명이 아니라 매칭 대상이 아님)\n")
    L.append("> **symptom 하위 태그** `symptom_kind`: 검사·검체 결과로만 확인되는 이상소견은 `lab_finding`, "
             "환자가 자각하거나 관찰 가능한 증상·징후는 `clinical`. "
             "판정 근거는 KCD R70-R94 대역(진단명 없는 임상 및 검사의 이상소견)이며, "
             "이 대역이 실제 인지 가능성과 어긋나는 문서는 본문 검토로 덮어씀(`symptom_kind_source` 참조)\n")

    L.append("\n## 1. 카테고리 분포 (재분류 후)\n")
    L.append("| category | 문서수 | 비율 |\n|---|---:|---:|")
    for k,v in cat_cnt.most_common():
        L.append(f"| {k} | {v} | {v/n*100:.1f}% |")
    L.append(f"\nconfidence: high {conf_cnt.get('high',0)} / medium {conf_cnt.get('medium',0)} / low {conf_cnt.get('low',0)}\n")

    L.append("\n## 2. 재분류 전(superclass) vs 후(category)\n")
    L.append("**기존 superclass 분포:** " + ", ".join(f"{k} {v}" for k,v in super_cnt.most_common()) + "\n")
    L.append("\n**교차표 (행=새 category, 열=기존 superclass):**\n")
    supers=[s for s,_ in super_cnt.most_common()]
    L.append("| category | " + " | ".join(supers) + " |")
    L.append("|---|" + "|".join(["---:"]*len(supers)) + "|")
    for cat,_ in cat_cnt.most_common():
        row=[str(crosstab[cat].get(s,0)) for s in supers]
        L.append(f"| {cat} | " + " | ".join(row) + " |")

    L.append(f"\n## 3. 기존 superclass와 불일치\n")
    L.append(f"- 불일치 문서: **{len(mism)}건** / {n}건 ({len(mism)/n*100:.1f}%) → `mismatch_review.csv`\n")
    mism_by=Counter((d.get('superclass'),d['category']) for d in mism)
    L.append("주요 이동:")
    for (s,c),v in mism_by.most_common(12):
        L.append(f"  - {s} → **{c}**: {v}건")

    L.append(f"\n## 4. KCD-9 매칭 성공률\n")
    L.append(f"**disease 문서: {len(dz_matched)}/{len(dz)}건 매칭 ({len(dz_matched)/len(dz)*100:.1f}%)**")
    L.append("- 문서 최상위 match_type: " + ", ".join(f"{k} {v}" for k,v in dz_best.most_common()))
    L.append(f"\n**symptom 문서: {len(sy_matched)}/{len(sy)}건 매칭 ({len(sy_matched)/max(1,len(sy))*100:.1f}%)**")
    L.append("- symptom_kind: " + ", ".join(f"{k} {v}" for k,v in sy_kind.most_common()))
    if sy_lab:
        L.append("- `lab_finding`(검사 이상소견): " +
                 ", ".join(f"{d.get('disease')}({','.join(m['code'] for m in d['kcd_matches'])})" for d in sy_lab))
    if sy_nolink:
        L.append("- KCD 연결 없음(자체·임베디드 모두): " +
                 ", ".join(f"{d.get('disease')}" for d in sy_nolink) + " → 사전 별칭 보강 필요")
    L.append(f"\n**임베디드 질환 청크: {len(emb_matched)}/{len(emb_all)}건 매칭 ({len(emb_matched)/max(1,len(emb_all))*100:.1f}%)**")
    L.append("- 청크 최상위 match_type: " + ", ".join(f"{k} {v}" for k,v in emb_best.most_common()))
    ov=[d for d in docs if d.get("kcd_override_reason")]
    if ov:
        L.append(f"\n**대체 질의어 예외 적용: {len(ov)}건** (`kcd_overrides.json`)")
        L.append("- matcher의 substring 계층은 휴리스틱이라 전역 규칙 변경이 다른 문서에 오류를 옮긴다. "
                 "개별 문서의 질의어를 지정해 처리한 건들:")
        for d in sorted(ov,key=lambda x:x["_file"]):
            L.append(f"  - {d.get('disease')} → " +
                     ", ".join(f"{m['code']}({m['korean_name']})" for m in d["kcd_matches"]))
    L.append("\n- 전체 후보 match_type 분포: " + ", ".join(f"{k} {v}" for k,v in cand_types.most_common()))
    L.append(f"- 매칭 실패(unmatched): disease 문서 {len(dz_unmatched)}건 + 임베디드 {len(emb_unmatched)}건 → `unmatched_kcd.csv`\n")

    L.append(f"\n## 5. 검수 대상\n")
    L.append(f"- category_confidence=low: **{len(low)}건** → `low_confidence.csv`")
    for d in sorted(low,key=lambda x:x["_file"]):
        L.append(f"  - {d.get('disease')} → {d['category']} ({d.get('category_source','')})")
    L.append(f"\n- 중복 섹션 제거된 문서: {len(dedup)}건")
    for d in dedup:
        L.append(f"  - {d.get('disease')}: {d['dedup_removed_sections']}개 섹션 제거")

    with open(os.path.join(REP,"summary_report.md"),"w",encoding="utf-8") as f:
        f.write("\n".join(L))

    print("리포트 생성 완료 ->", REP)
    print(f"  disease 매칭 {len(dz_matched)}/{len(dz)} ({len(dz_matched)/len(dz)*100:.1f}%)")
    print(f"  임베디드 매칭 {len(emb_matched)}/{len(emb_all)}")
    print(f"  mismatch {len(mism)} / low {len(low)} / dedup {len(dedup)}")
    print("  후보 match_type:", dict(cand_types))

if __name__=="__main__":
    main()
