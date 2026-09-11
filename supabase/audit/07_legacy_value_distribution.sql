-- 작성자: 김진우
-- 값 변환 규칙을 정하기 위한 코드·단위 분포만 집계한다. 사용자 원문은 반환하지 않는다.
select 'lifestyle_activity.source' as field, source::text as value, count(*) as row_count
from public.lifestyle_activity group by source
union all
select 'lifestyle_exercise.source', coalesce(source::text, '<NULL>'), count(*)
from public.lifestyle_exercise group by source
union all
select 'lifestyle_exercise.exercise_type', coalesce(exercise_type::text, '<NULL>'), count(*)
from public.lifestyle_exercise group by exercise_type
union all
select 'lifestyle_bio.source', coalesce(source::text, '<NULL>'), count(*)
from public.lifestyle_bio group by source
union all
select 'lifestyle_bio.bio_type', coalesce(bio_type::text, '<NULL>'), count(*)
from public.lifestyle_bio group by bio_type
union all
select 'lifestyle_bio.unit', coalesce(unit::text, '<NULL>'), count(*)
from public.lifestyle_bio group by unit
union all
select 'lifestyle_nutrition.source', coalesce(source::text, '<NULL>'), count(*)
from public.lifestyle_nutrition group by source
union all
select 'lifestyle_nutrition.nutrition_type', coalesce(nutrition_type::text, '<NULL>'), count(*)
from public.lifestyle_nutrition group by nutrition_type
order by field, value;
