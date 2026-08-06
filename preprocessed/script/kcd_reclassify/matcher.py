# -*- coding: utf-8 -*-
"""KCD-9 코드 매칭기.
매칭 우선순위: ① exact(괄호유지 정확일치) ② paren(괄호제거 후 일치) ③ alias(이명 일치)
                ④ fuzzy(rapidfuzz 유사도 임계값 이상)
결과가 여러 개면 전부 후보로 반환(억지로 하나로 강제하지 않음)."""
import json, os, re
from rapidfuzz import process, fuzz

_HERE = os.path.dirname(os.path.abspath(__file__))

def strip_paren(s):
    return re.sub(r"[\(\[\{（【].*?[\)\]\}）】]", "", s or "")

def norm_key(s):
    s = strip_paren(s or "")
    s = s.replace(" ", "").strip()
    s = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ0-9]+\.", "", s)
    return s.strip()

def raw_key(s):
    return str(s or "").replace(" ", "").strip()

# 부분문자열 오탐(WRatio) 방지 위해 전체 문자열 유사도(ratio) 사용.
FUZZY_THRESHOLD = 85   # 0~100 (fuzz.ratio)

class KCDMatcher:
    def __init__(self, dict_path=None):
        with open(dict_path or os.path.join(_HERE, "kcd_dict.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.name_map = d["name_map"]
        self.raw_map  = d["raw_map"]
        self.code_info = d["code_info"]
        self._fuzzy_keys = list(self.name_map.keys())

    def _entries(self, entries, mtype):
        out=[]
        for e in entries:
            t = "alias" if e["is_alias"] else mtype
            out.append({"code": e["code"], "level": e["level"],
                        "korean_name": e["korean_name"], "match_type": t})
        return out

    @staticmethod
    def _dedup(cands):
        seen=set(); out=[]
        # exact > paren > alias > fuzzy 우선순위로 정렬 후 코드 중복 제거
        order={"exact":0,"paren":1,"alias":2,"substring":3,"fuzzy":4}
        for c in sorted(cands, key=lambda x: order.get(x["match_type"],9)):
            if c["code"] in seen: continue
            seen.add(c["code"]); out.append(c)
        return out

    def _substring_candidates(self, qstrip, max_len_gap=6, limit=3):
        """질의어가 KCD명에 '포함'되는 안전한 방향의 부분매칭.
        (짧은 KCD명이 긴 질의어에 포함되는 반대방향은 오탐이므로 사용 안 함)."""
        if len(qstrip) < 3:
            return []
        hits=[]
        for key in self._fuzzy_keys:
            if qstrip in key and len(key) > len(qstrip):
                gap = len(key) - len(qstrip)
                if gap <= max_len_gap:
                    hits.append((gap, key))
        hits.sort(key=lambda x: x[0])
        out=[]
        for _, key in hits[:limit]:
            for e in self.name_map[key]:
                out.append({"code": e["code"], "level": e["level"],
                            "korean_name": e["korean_name"], "match_type": "substring"})
        return out

    def match(self, name):
        name = (name or "").strip()
        if not name:
            return []
        qraw = raw_key(name)
        # ① exact (괄호 유지)
        if qraw in self.raw_map:
            return self._dedup(self._entries(self.raw_map[qraw], "exact"))
        # ② paren 제거 후 일치
        qstrip = norm_key(name)
        if qstrip and qstrip in self.name_map:
            return self._dedup(self._entries(self.name_map[qstrip], "paren"))
        # ③ 부분매칭(질의어 ⊂ KCD명): 더 구체적인 하위코드로 매칭
        if qstrip:
            sub = self._substring_candidates(qstrip)
            if sub:
                return self._dedup(sub)
        # ④ fuzzy(전체 문자열 유사도, 오탈자/이형)
        if qstrip:
            hits = process.extract(qstrip, self._fuzzy_keys, scorer=fuzz.ratio,
                                   limit=3, score_cutoff=FUZZY_THRESHOLD)
            cands=[]
            for key, score, _ in hits:
                for e in self.name_map[key]:
                    cands.append({"code": e["code"], "level": e["level"],
                                  "korean_name": e["korean_name"],
                                  "match_type": "fuzzy", "score": round(score,1)})
            if cands:
                return self._dedup(cands)
        return []
