"""Every sentence the agent relays to a person, in both languages.

Two different languages are in play in one run and they are **not** the same
setting:

* ``--language vi|en`` is the language *printed on the map*, handled by
  :mod:`i18n`. It follows the audience of the finished figure.
* the message language here is the language of the *conversation*: the warnings,
  the reasons behind a recommendation, the verdict on a sheet. It follows the
  person the agent is talking to.

They come apart in practice — an English-speaking programme officer producing a
Vietnamese map for a provincial health department is the ordinary case, not the
exotic one — so they are separate flags.

Every sentence lives here once, with its two languages side by side, keyed by
the same id the warning already carries. Keeping them in one table is the point:
this project has twice shipped a half-translation because the same decision was
written down in two places, and a warning whose Vietnamese and English differ in
meaning is worse than one that is only Vietnamese. ``tests/test_messages.py``
walks this table and fails if a key is missing a language or if the two versions
do not take the same placeholders.

The JSON *keys* are English (``problem``, ``why``, ``fix``). They are
read by the agent, never shown to a user, and renaming them would break the
output contract for no reader's benefit.
"""

from __future__ import annotations

import re
from typing import Any

DEFAULT = "vi"
LANGUAGES = ("vi", "en")

_current = DEFAULT


def normalise(lang: str | None) -> str:
    lang = (lang or _current).strip().lower()
    return lang if lang in LANGUAGES else DEFAULT


def use(lang: str | None) -> str:
    """Set the conversation language for this run; return the previous one.

    One CLI invocation serves one request in one language, so this is a property
    of the run rather than of any single call. Tests restore the old value with
    the return.
    """
    global _current
    previous = _current
    _current = normalise(lang)
    return previous


def current() -> str:
    return _current


WHAT, WHY, FIX = "problem", "why", "fix"

#: Optional overrides used when the sentence counts exactly one thing. English
#: inflects its nouns and verbs and Vietnamese does not, so "1 place names were
#: matched" is a defect that only exists on one side of the table. The override
#: sits beside the plural form rather than in a rule engine: there are two
#: languages here, not forty, and a sentence a reader can check beats a rule they
#: cannot. Vietnamese entries carry no override, which is not an omission.
ONE = "one"


#: Sentence fragments that are glued into a larger sentence rather than standing
#: on their own. Kept here so a clause does not end up in one language inside a
#: sentence in the other.
FRAGMENTS: dict[str, dict[str, str]] = {
    "numerator": {"vi": "tử số", "en": "numerator"},
    "denominator": {"vi": "mẫu số", "en": "denominator"},

    "commune-place-column": {
        "vi": "Cột địa danh cấp xã ",
        "en": "The commune name column ",
    },
    "the-named-column": {
        "vi": "Cột '{column}' ",
        "en": "Column '{column}' ",
    },
    "ambiguous-dropped": {
        "vi": " Những dòng này đã bị để ra ngoài bản đồ, nên xã tương ứng hiện màu "
              "xám 'chưa có số liệu'.",
        "en": " These rows were left off the map, so the communes concerned appear "
              "grey, as 'no data'.",
    },
    "ambiguous-kept": {
        "vi": " Những dòng này VẪN được vẽ theo phương án đầu tiên trong "
              "'candidates' — tức một phỏng đoán, và bản đồ sẽ không có dấu hiệu "
              "gì cho thấy điều đó.",
        "en": " These rows WERE still drawn, using the first entry in "
              "'candidates' — that is a guess, and nothing on the map marks it "
              "as one.",
    },
}


#: One entry per warning id. ``{placeholders}`` must match between the two
#: languages; the test suite enforces that.
ISSUES: dict[str, dict[str, dict[str, str]]] = {
    "detached-land-no-inset": {
        "vi": {
            WHAT: "Phần đất chính chỉ chiếm {width} bề ngang khung bản đồ.",
            WHY: "Quốc gia này có đất nằm xa phần đất chính, và khung phải giãn ra để "
                 "chứa hết, nên {lost} bề ngang trang giấy là biển. Vùng người đọc "
                 "thực sự nhìn vào bị thu nhỏ lại tương ứng.",
            FIX: "Nếu phần đất xa nằm hẳn về một phía theo kinh độ, khai kinh tuyến "
                 "chia trong hồ sơ quốc gia ({field}) để nó vào khung phụ. Nếu không "
                 "tách được bằng một kinh tuyến, cân nhắc vẽ riêng phần đất chính, "
                 "hoặc giữ khung rộng nếu các vùng xa chính là điều bản đồ muốn nói.",
        },
        "en": {
            WHAT: "The main body of land occupies only {width} of the map frame's width.",
            WHY: "This country has land far from its main body and the frame has to "
                 "stretch to hold it, so {lost} of the page width is sea. The part the "
                 "reader is actually looking at shrinks by the same amount.",
            FIX: "If the distant land lies wholly to one side by longitude, declare the "
                 "dividing meridian in the country profile ({field}) and it goes to an "
                 "inset. If one meridian cannot separate it, consider drawing the main "
                 "body on its own, or keep the wide frame if the distant land is what "
                 "the map is about.",
        },
    },
    "low-coverage": {
        "vi": {
            WHAT: "Chỉ {with_data}/{in_frame} đơn vị trong khung bản đồ có số liệu ({share}).",
            WHY: "Bản đồ tô màu vùng khiến người xem tưởng cả khu vực đã được khảo sát. "
                 "Phần lớn bản đồ sẽ là màu xám, và vài vùng có màu dễ bị đọc thành 'điểm nóng'.",
            FIX: "Cân nhắc: (1) vẽ bản đồ ký hiệu điểm/vòng tròn thay vì tô màu vùng, "
                 "(2) chỉ vẽ các đơn vị có số liệu, hoặc (3) gộp lên cấp tỉnh nếu số liệu cấp xã quá thưa. "
                 "Nếu vẫn tô màu vùng, phải ghi rõ 'xám = chưa khảo sát, không phải bằng 0'.",
        },
        "en": {
            ONE: {WHAT: "Only {with_data} of the {in_frame} units in the map frame has "
                        "data ({share})."},
            WHAT: "Only {with_data} of the {in_frame} units in the map frame have data ({share}).",
            WHY: "A choropleth reads as though the whole area had been surveyed. Most of the map "
                 "will be grey, and the few coloured units are easily read as hotspots.",
            FIX: "Consider: (1) a point or proportional-circle map instead of a choropleth, "
                 "(2) mapping only the units that have data, or (3) aggregating to province level "
                 "if the commune data is this sparse. If you keep the choropleth, state plainly "
                 "that 'grey = not surveyed, not zero'.",
        },
    },
    "summing-a-rate": {
        "vi": {
            WHAT: "Đang cộng dồn '{column}' cho các dòng trùng địa danh.",
            WHY: "Cộng hai tỷ lệ với nhau không tạo ra tỷ lệ có nghĩa: 60% + 70% không phải 130%. "
                 "Kết quả trên bản đồ sẽ sai hoàn toàn.",
            FIX: "Dùng trung bình có trọng số theo dân số/mẫu số, hoặc tính lại từ tử số và mẫu số gốc.",
        },
        "en": {
            WHAT: "'{column}' is being summed across rows that share a place name.",
            WHY: "Adding two rates does not produce a rate: 60% + 70% is not 130%. The values on "
                 "the map would be simply wrong.",
            FIX: "Use a mean weighted by population or by the denominator, or recompute from the "
                 "original numerator and denominator.",
        },
    },
    "unweighted-mean": {
        "vi": {
            WHAT: "Đang lấy trung bình đơn giản của '{column}'.",
            WHY: "Một xã 2.000 dân và một xã 100.000 dân đang được tính ngang nhau, "
                 "nên con số chung có thể lệch khỏi thực tế.",
            FIX: "Nếu bảng có cột dân số hoặc mẫu số, hãy dùng trung bình có trọng số.",
        },
        "en": {
            WHAT: "'{column}' is being averaged without weights.",
            WHY: "A commune of 2,000 people and one of 100,000 currently count the same, so the "
                 "combined figure can sit some way from the real one.",
            FIX: "If the table has a population or denominator column, use a weighted mean.",
        },
    },
    "colour-by-count": {
        "vi": {
            WHAT: "Đang tô màu vùng theo '{column}', vốn là số đếm thô.",
            WHY: "Vùng rộng gần như luôn có số đếm lớn hơn vùng hẹp, nên bản đồ sẽ phản ánh diện tích "
                 "và dân số nhiều hơn là mức độ nghiêm trọng thật.",
            FIX: "Nên tô màu theo tỷ lệ hoặc tỷ suất trên dân số, và thể hiện số đếm bằng kích thước vòng tròn.",
        },
        "en": {
            WHAT: "'{column}' is a raw count, and it is being used to colour the areas.",
            WHY: "A large area almost always carries a larger count than a small one, so the map "
                 "would show area and population rather than the severity of the problem.",
            FIX: "Colour by a rate or a per-capita figure, and show the count through circle size.",
        },
    },
    "percent-over-100": {
        "vi": {
            WHAT: "'{column}' có giá trị tới {value}%.",
            WHY: "Tỷ lệ vượt 100% thường do mẫu số sai hoặc do cột này thực ra không phải phần trăm.",
            FIX: "Kiểm tra lại cột mẫu số, hoặc xác nhận đơn vị của cột này với người lập bảng.",
        },
        "en": {
            WHAT: "'{column}' reaches {value}%.",
            WHY: "A share above 100% usually means the wrong denominator, or that this column is "
                 "not a percentage at all.",
            FIX: "Check the denominator column, or confirm the unit of this column with whoever "
                 "compiled the table.",
        },
    },
    "percent-negative": {
        "vi": {
            WHAT: "'{column}' có giá trị âm ({value}%).",
            WHY: "Tỷ lệ âm không có nghĩa, trừ khi đây là mức thay đổi.",
            FIX: "Nếu là mức thay đổi, hãy đổi sang bản đồ thay đổi với thang màu hai chiều.",
        },
        "en": {
            WHAT: "'{column}' goes negative ({value}%).",
            WHY: "A negative share is meaningless unless the column is a change rather than a level.",
            FIX: "If it is a change, switch to a change map with a diverging colour ramp.",
        },
    },
    "classes-adjusted": {
        "vi": {
            WHAT: "Đã điều chỉnh cách chia nhóm.",
            WHY: "{note}",
            FIX: "Không cần làm gì; ghi chú này chỉ để minh bạch.",
        },
        "en": {
            WHAT: "The class breaks were adjusted.",
            WHY: "{note}",
            FIX: "No action needed; this note is here for transparency.",
        },
    },
    "too-many-classes": {
        "vi": {
            WHAT: "Chia {classes} nhóm cho chỉ {observations} đơn vị có số liệu.",
            WHY: "Mỗi nhóm chỉ còn một hai đơn vị, nên ranh giới màu phản ánh ngẫu nhiên hơn là quy luật.",
            FIX: "Giảm còn {suggest} nhóm để bản đồ đọc được rõ ràng hơn.",
        },
        "en": {
            ONE: {WHAT: "{classes} classes for only {observations} unit with data."},
            WHAT: "{classes} classes for only {observations} units with data.",
            WHY: "That leaves one or two units per class, so the colour breaks track noise rather "
                 "than any pattern.",
            FIX: "Drop to {suggest} classes so the map reads clearly.",
        },
    },
    "spread-too-small": {
        "vi": {
            WHAT: "Chênh lệch giữa đơn vị cao nhất và thấp nhất chỉ {span} trên nền giá trị khoảng {scale}.",
            WHY: "Thang màu trải hết trên một khoảng chênh rất nhỏ, nên bản đồ trông như "
                 "các đơn vị khác nhau rõ rệt trong khi thực tế gần như bằng nhau. Người "
                 "đọc sẽ diễn giải màu đậm nhạt thành khác biệt có ý nghĩa.",
            FIX: "Cân nhắc: nói rõ khoảng giá trị ngay trong tiêu đề hoặc câu nhận định, "
                 "giảm còn 2–3 nhóm, hoặc chọn chỉ số khác nếu chỉ số này đã bão hoà.",
        },
        "en": {
            WHAT: "The highest and lowest units differ by only {span}, on values of about {scale}.",
            WHY: "The full colour ramp is stretched across a difference that is barely there, so "
                 "the map looks as though the units differ markedly when they are almost equal. "
                 "A reader will take the light and dark shades for a meaningful gap.",
            FIX: "Consider: state the value range in the title or the insight line, drop to 2–3 "
                 "classes, or choose another indicator if this one has saturated.",
        },
    },
    "may-not-be-commune-level": {
        "vi": {
            WHAT: "{unmatched}/{total} tên trong bảng không phải tên xã hiện nay.",
            WHY: "{where}có thể là **cấp huyện** — tầng hành chính đã bỏ từ 2025 và không "
                 "có trong shapefile. Nhiều huyện trùng tên với một xã, nên phần khớp được "
                 "sẽ hiện là 'khớp chắc chắn' nhưng lại rơi vào một xã khác hẳn về phạm vi.",
            FIX: "Kiểm tra vài tên trong match_review.csv xem có đúng là xã không. Nếu là "
                 "huyện, hãy vẽ ở cấp tỉnh (--admin-level province) và nói rõ với người dùng.",
        },
        "en": {
            ONE: {WHAT: "{unmatched} of {total} names in the table is not a current "
                        "commune name."},
            WHAT: "{unmatched} of {total} names in the table are not current commune names.",
            WHY: "{where}may hold **districts** — a tier abolished in 2025 that is not in the "
                 "shapefile. Many districts share a name with a commune, so the names that do "
                 "match are reported as certain while landing on a unit of a quite different size.",
            FIX: "Check a few names in match_review.csv against the commune list. If they are "
                 "districts, map at province level (--admin-level province) and say so to the user.",
        },
    },
    "unmatched-rows": {
        "vi": {
            WHAT: "{count} địa danh trong bảng không tìm thấy trên bản đồ.",
            WHY: "Những dòng này sẽ biến mất khỏi bản đồ, khiến tổng số trên bản đồ nhỏ hơn tổng trong bảng.",
            FIX: "Xem file match_review.csv, sửa lại chính tả tên hoặc xác nhận tên đúng trước khi vẽ.",
        },
        "en": {
            ONE: {WHAT: "{count} place name in the table was not found on the map."},
            WHAT: "{count} place names in the table were not found on the map.",
            WHY: "Those rows drop off the map, so the totals shown are lower than the totals in "
                 "the table.",
            FIX: "Open match_review.csv, correct the spelling, or confirm the intended name before "
                 "drawing.",
        },
    },
    "merger-converted": {
        "vi": {
            WHAT: "{count} tên tỉnh cũ đã được quy đổi về tỉnh hiện nay.",
            WHY: "Bảng dùng tên trước đợt sáp nhập 2025. Nếu không quy đổi, các tỉnh cũ sẽ "
                 "biến mất khỏi bản đồ 34 tỉnh.",
            FIX: "Không cần làm gì. Lưu ý: số đếm của các tỉnh cũ được cộng lại, còn tỷ lệ "
                 "được tính lại theo trọng số chứ không lấy trung bình đơn giản.",
        },
        "en": {
            ONE: {WHAT: "{count} former province name was mapped onto the present provinces."},
            WHAT: "{count} former province names were mapped onto the present provinces.",
            WHY: "The table uses the names from before the 2025 mergers. Without the crosswalk "
                 "those provinces would vanish from the 34-province map.",
            FIX: "No action needed. Note that counts for the former provinces were added together, "
                 "while rates were recomputed with weights rather than averaged.",
        },
    },
    "ambiguous-match": {
        "vi": {
            WHAT: "{count} địa danh khớp với nhiều xã khác nhau trong cùng tỉnh.",
            WHY: "Sau khi bỏ dấu, một số tên trở nên giống hệt nhau — ví dụ 'Cẩm Giang' và "
                 "'Cẩm Giàng' ở Hải Phòng. Máy không thể tự biết bảng của bạn đang nói tới xã nào.{tail}",
            FIX: "Mở match_review.csv, xem cột 'candidates' để biết các xã có thể, rồi ghi rõ "
                 "tên đầy đủ có dấu vào bảng dữ liệu, hoặc chốt bằng lệnh fix-match. Muốn giữ "
                 "nguyên phỏng đoán thì chạy render với --ambiguous keep.",
        },
        "en": {
            ONE: {WHAT: "{count} place name matches several different communes within the "
                        "same province."},
            WHAT: "{count} place names match several different communes within the same province.",
            WHY: "Stripped of their diacritics some names become identical — 'Cẩm Giang' and "
                 "'Cẩm Giàng' in Hải Phòng, for instance. Nothing in the data says which commune "
                 "your table means.{tail}",
            FIX: "Open match_review.csv, read the 'candidates' column for the possibilities, then "
                 "write the full name with diacritics into the data, or settle it with the "
                 "fix-match command. To keep the guess, run render with --ambiguous keep.",
        },
    },
    "match-needs-review": {
        "vi": {
            WHAT: "{count} địa danh được ghép bằng cách đoán gần đúng.",
            WHY: "Tên gần giống nhau có thể bị ghép nhầm sang xã khác cùng tỉnh.",
            FIX: "Duyệt các dòng có ghi chú 'fuzzy' trong match_review.csv trước khi vẽ.",
        },
        "en": {
            ONE: {WHAT: "{count} place name was matched by approximation."},
            WHAT: "{count} place names were matched by approximation.",
            WHY: "Names that look alike can be matched onto the wrong commune of the same province.",
            FIX: "Review the rows marked 'fuzzy' in match_review.csv before drawing.",
        },
    },
    "several-periods": {
        "vi": {
            WHAT: "Bảng chứa {count} kỳ báo cáo khác nhau.",
            WHY: "Nếu vẽ chung, số liệu của nhiều kỳ sẽ bị cộng dồn vào một xã và con số sẽ bị thổi phồng.",
            FIX: "Chọn một kỳ để vẽ, hoặc dùng bản đồ so sánh hai kỳ, hoặc dàn nhiều kỳ cạnh nhau chung thang màu.",
        },
        "en": {
            WHAT: "The table holds {count} different reporting periods.",
            WHY: "Mapped together, several periods are summed into one unit and the figures come "
                 "out inflated.",
            FIX: "Pick one period, use a two-period change map, or lay the periods side by side on "
                 "a shared colour scale.",
        },
    },
    "circles-hide-areas": {
        "vi": {
            WHAT: "Vòng tròn lớn hơn chính đơn vị hành chính nó đại diện.",
            WHY: "Vòng tròn sẽ che mất màu bên dưới và tràn sang xã bên cạnh, khiến người xem đọc nhầm vùng.",
            FIX: "Thu nhỏ vòng tròn tối đa, hoặc bỏ lớp vòng tròn và tách thành hai bản đồ nhỏ cạnh nhau.",
        },
        "en": {
            WHAT: "The circles are larger than the administrative units they stand for.",
            WHY: "A circle hides the colour beneath it and spills over the neighbouring commune, so "
                 "readers attribute it to the wrong unit.",
            FIX: "Reduce the maximum circle size, or drop the circle layer and use two smaller maps "
                 "side by side.",
        },
    },
    "needs-diverging-scale": {
        "vi": {
            WHAT: "Số liệu có cả giá trị tăng và giảm.",
            WHY: "Thang màu một chiều sẽ không cho thấy đâu là ranh giới giữa tăng và giảm.",
            FIX: "Dùng thang màu hai chiều với điểm giữa tại 0.",
        },
        "en": {
            WHAT: "The data contains both increases and decreases.",
            WHY: "A sequential ramp gives no indication of where rise turns into fall.",
            FIX: "Use a diverging ramp anchored at 0.",
        },
    },
    "sheet-not-mappable": {
        # ``why`` and ``fix`` are the verdict from :mod:`tabular`, already in the
        # right language; this entry only supplies the sentence around them
        "vi": {
            WHAT: "Sheet này không dùng để vẽ bản đồ được.",
            WHY: "{why}",
            FIX: "{fix}",
        },
        "en": {
            WHAT: "This sheet cannot be used to draw a map.",
            WHY: "{why}",
            FIX: "{fix}",
        },
    },
    "long-table-double-count": {
        "vi": {
            WHAT: "Bảng dạng dài: một đơn vị nằm trên nhiều dòng.",
            WHY: "{why}",
            FIX: "Truyền --where 'CỘT=GIÁ TRỊ' cho từng cột nêu trên khi render.",
        },
        "en": {
            WHAT: "Long table: one unit spans several rows.",
            WHY: "{why}",
            FIX: "Pass --where 'COLUMN=VALUE' for each of the columns named above when rendering.",
        },
    },
    "unreadable-periods": {
        "vi": {
            WHAT: "{count} giá trị kỳ không đọc được ngày tháng: {periods}.",
            WHY: "Những kỳ này bị xếp xuống cuối, nên thứ tự thời gian trong video có thể sai.",
            FIX: "Ghi kỳ theo dạng 'Năm 2024', 'Quý I/2026' hoặc 'Tháng 3/2026'.",
        },
        "en": {
            ONE: {WHAT: "{count} period value could not be read as a date: {periods}."},
            WHAT: "{count} period values could not be read as dates: {periods}.",
            WHY: "They are sorted to the end, so the chronological order in the animation may be wrong.",
            FIX: "Write periods in the form 'Năm 2024', 'Quý I/2026' or 'Tháng 3/2026'.",
        },
    },
    "mostly-missing": {
        "vi": {
            WHAT: "Cột '{column}' thiếu {share} số dòng.",
            WHY: "Bản đồ sẽ có nhiều vùng xám và dễ bị hiểu là chưa có vấn đề gì ở đó.",
            FIX: "Xác nhận đây là 'chưa khảo sát' hay 'bằng 0' trước khi vẽ.",
        },
        "en": {
            WHAT: "Column '{column}' is missing in {share} of the rows.",
            WHY: "The map will carry a lot of grey, which readers tend to read as 'nothing wrong here'.",
            FIX: "Confirm whether that means 'not surveyed' or 'zero' before drawing.",
        },
    },
}


#: Standalone sentences that are not part of a three-part warning: the verdict on
#: a sheet, the note explaining an automatic classification change, the reason
#: behind a recommended slice. Same rule as ``ISSUES`` — both languages, matching
#: placeholders, one place.
TEXT: dict[str, dict[str, str]] = {
    # --- verdict on a sheet, from tabular.usability ------------------------
    "sheet-no-data-rows.reason": {
        "vi": "Sheet không có dòng dữ liệu nào.",
        "en": "The sheet has no data rows.",
    },
    "sheet-no-data-rows.fix": {
        "vi": "Chọn sheet khác trong workbook.",
        "en": "Choose another sheet in the workbook.",
    },
    "unnamed-columns.reason": {
        "vi": "{unnamed}/{total} cột không có tên ({examples}…).",
        "en": "{unnamed} of {total} columns have no name ({examples}…).",
    },
    "unnamed-columns.fix": {
        "vi": "Sheet này nhiều khả năng là bảng tổng hợp (pivot) hoặc có "
              "dòng tiêu đề/ghi chú ở đầu. Chọn sheet chứa bảng dữ liệu thô, "
              "hoặc xoá các dòng thừa phía trên bảng rồi lưu lại.",
        "en": "This is most likely a pivot table, or it carries title and note "
              "rows above the data. Choose the sheet holding the raw table, or "
              "delete the rows above the table and save again.",
    },
    "no-place-column.reason": {
        "vi": "Không tìm thấy cột nào chứa tên tỉnh/thành phố hoặc xã/phường.",
        "en": "No column was found holding province or commune names.",
    },
    "no-place-column.fix": {
        "vi": "Bản đồ cần một cột địa danh để ghép với shapefile. Kiểm tra "
              "xem sheet có cột tên địa phương không, hoặc chỉ định bằng "
              "--province-column / --commune-column.",
        "en": "A map needs a place-name column to join to the shapefile. Check "
              "whether the sheet has one, or name it with --province-column / "
              "--commune-column.",
    },
    "sheet-empty.reason": {
        "vi": "Sheet trống.",
        "en": "The sheet is empty.",
    },
    "sheet-empty.fix": {
        "vi": "Bỏ qua sheet này.",
        "en": "Skip this sheet.",
    },

    # --- notes on an automatic classification change -----------------------
    "bins.fewer-classes": {
        "vi": "Giảm từ {asked} xuống {classes} nhóm vì chỉ có {distinct} giá trị khác nhau.",
        "en": "Reduced from {asked} to {classes} classes: there are only {distinct} distinct values.",
    },
    "bins.sequential": {
        "vi": "Số liệu chỉ có một chiều tăng hoặc giảm nên dùng thang một chiều.",
        "en": "The data moves in one direction only, so a sequential ramp is used.",
    },
    "bins.classes-merged": {
        "vi": "Gộp còn {classes} nhóm để tránh khoảng quá hẹp, không phản ánh khác biệt thật.",
        "en": "Merged down to {classes} classes to avoid bands too narrow to stand for a real difference.",
    },
    "bins.diverging-around-zero": {
        "vi": "Thang màu hai chiều được neo tại 0, nên màu trung tính đúng nghĩa là không đổi.",
        "en": "The diverging ramp is anchored at 0, so the neutral colour means exactly 'no change'.",
    },
    "bins.shared-scale": {
        "vi": "Dùng chung thang phân lớp cho tất cả bản đồ trong loạt để so sánh được giữa các tỉnh.",
        "en": "One set of breaks is shared by every map in the series, so the provinces stay comparable.",
    },

    # --- how the variables were laid out over the two channels -------------
    "channel.split-plates": {
        # the channel names are spelled out here rather than interpolated from
        # FILL/SYMBOL: those two are machine keys in the JSON and must not move
        "vi": "Một tấm bản đồ chỉ có hai kênh: màu vùng và vòng tròn. {maps} tấm vì các "
              "biến còn lại tranh cùng một kênh — chúng nằm chung thư mục và chung "
              "trang HTML, chuyển qua lại bằng hộp chọn.",
        "en": "One map carries two channels: the area fill and the circles. It takes "
              "{maps} maps because the remaining variables compete for the same channel — "
              "they share a folder and a single HTML page, switched with the picker.",
    },
    "channel.fill": {
        "vi": "'{name}' tô màu vùng vì đã chuẩn hoá ({semantic}), nên so được giữa tỉnh "
              "to và tỉnh nhỏ.",
        "en": "'{name}' colours the areas because it is normalised ({semantic}), so large "
              "and small provinces stay comparable.",
    },
    "channel.circles": {
        "vi": "'{name}' vẽ vòng tròn vì là số đếm — tô màu vùng theo số đếm sẽ thành vẽ "
              "diện tích và dân số.",
        "en": "'{name}' is drawn as circles because it is a count — colouring areas by a "
              "count would map area and population instead.",
    },
    "channel.no-fill": {
        "vi": "Không có biến nào tô màu được, nên nền để trắng và chỉ vẽ vòng tròn.",
        "en": "No variable can carry the fill, so the base stays white and only the "
              "circles are drawn.",
    },
    "channel.not-a-quantity": {
        "vi": "'{name}' là {semantic}, không phải một đại lượng để vẽ. Cột thời gian dùng "
              "để lọc kỳ hoặc dựng bản đồ theo thời gian.",
        "en": "'{name}' is {semantic}, not a quantity to map. A time column is for "
              "selecting a period or building a map over time.",
    },
    "channel.is-a-coordinate": {
        "vi": "'{name}' là toạ độ — dùng cho bản đồ điểm (--map-type point), không phải "
              "một kênh của bản đồ vùng.",
        "en": "'{name}' is a coordinate — that belongs to a point map (--map-type point), "
              "not to a channel of an area map.",
    },
    "channel.meaning-unclear": {
        "vi": "'{name}' không có ngữ nghĩa đo lường rõ ràng ({semantic}).",
        "en": "'{name}' has no clear measurement meaning ({semantic}).",
    },
    "channel.unclear": {
        "vi": "không rõ",
        "en": "unknown",
    },
    "channel.fill-taken": {
        "vi": "{count} biến cùng đòi kênh màu vùng ({names}). Một tấm chỉ tô được một "
              "thang màu; các biến sau sẽ sang tấm riêng.",
        "en": "{count} variables want the fill channel ({names}). One map carries a single "
              "colour scale, so the later ones move to maps of their own.",
    },
    "channel.circles-taken": {
        "vi": "{count} biến cùng đòi kênh vòng tròn ({names}). Hai bộ vòng tròn chồng lên "
              "nhau thì không đọc được kích thước nào ra kích thước nào; các biến sau sẽ "
              "sang tấm riêng.",
        "en": "{count} variables want the circle channel ({names}). Two sets of circles "
              "overlaid leave no way to tell one size from the other, so the later ones "
              "move to maps of their own.",
    },
    "channel.fill-line": {
        "vi": "màu = {name}",
        "en": "fill = {name}",
    },
    "channel.circles-line": {
        "vi": "vòng tròn = {name}",
        "en": "circles = {name}",
    },
    "channel.line-prefix": {
        "vi": "Bản đồ {n}: ",
        "en": "Map {n}: ",
    },
    "channel.category-mixed-with-continuous": {
        "vi": "Trộn biến phân loại với biến liên tục trên cùng kênh màu: hai loại thang "
              "màu khác hẳn nhau, nên chúng phải nằm ở hai tấm.",
        "en": "A categorical and a continuous variable are sharing the fill channel: the "
              "two kinds of colour scale are quite different, so they belong on two maps.",
    },

    # --- the ranked map options in a profile -------------------------------
    "tier.commune": {"vi": "xã/phường", "en": "commune"},
    "tier.province": {"vi": "tỉnh/thành phố", "en": "province"},
    "option.choropleth-symbol.name": {
        "vi": "Bản đồ tô màu kèm vòng tròn",
        "en": "Choropleth with proportional circles",
    },
    "option.choropleth-symbol.why": {
        "vi": "Màu cho biết mức độ ({fill}) — so sánh được giữa các {level} to nhỏ khác "
              "nhau; vòng tròn cho biết quy mô thực tế ({symbol}).",
        "en": "Colour carries the level ({fill}), which stays comparable across {level}s of "
              "different size; the circles carry the actual scale ({symbol}).",
    },
    "option.choropleth.name": {
        "vi": "Bản đồ tô màu theo mức độ",
        "en": "Choropleth by level",
    },
    "option.choropleth.why": {
        "vi": "'{fill}' đã được chuẩn hoá theo dân số hoặc mẫu số, nên tô màu vùng là cách "
              "đọc công bằng giữa các {level}.",
        "en": "'{fill}' is normalised by population or by a denominator, so an area fill "
              "reads fairly across {level}s.",
    },
    "option.graduated-symbol.name": {
        "vi": "Bản đồ vòng tròn theo số lượng",
        "en": "Proportional circle map",
    },
    "option.graduated-symbol.why": {
        "vi": "'{symbol}' là số đếm; tô màu vùng sẽ thiên vị nơi rộng và đông dân, còn vòng "
              "tròn thể hiện đúng số lượng.",
        "en": "'{symbol}' is a count; an area fill would favour large and populous places, "
              "while circles show the quantity as it is.",
    },
    "option.change.name": {
        "vi": "Bản đồ mức thay đổi",
        "en": "Change map",
    },
    "option.change.why": {
        "vi": "'{fill}' có cả tăng và giảm, hợp với thang màu hai chiều để thấy ngay nơi đi "
              "lên và nơi đi xuống.",
        "en": "'{fill}' contains both rises and falls, which suits a diverging ramp that "
              "shows at a glance where it went up and where it went down.",
    },
    "option.categorized.name": {
        "vi": "Bản đồ phân loại theo nhóm",
        "en": "Categorical map",
    },
    "option.categorized.why": {
        "vi": "'{fill}' chỉ có {levels} nhóm, hợp để tô mỗi nhóm một màu riêng.",
        "en": "'{fill}' has only {levels} categories, few enough to give each its own colour.",
    },
    "option.point.name": {
        "vi": "Bản đồ điểm theo toạ độ",
        "en": "Point map from coordinates",
    },
    "option.point.why": {
        "vi": "Bảng có cột kinh độ và vĩ độ, nên có thể chấm đúng vị trí từng điểm thay vì "
              "tô cả vùng.",
        "en": "The table carries longitude and latitude, so each location can be plotted "
              "where it actually is instead of filling a whole area.",
    },
    "option.boundary.name": {
        "vi": "Bản đồ ranh giới tham chiếu",
        "en": "Reference boundary map",
    },
    "option.boundary.why": {
        "vi": "Chưa tìm thấy cột số liệu hay cột phân loại rõ ràng để thể hiện.",
        "en": "No clear numeric or categorical column was found to map.",
    },
    "semantic-source.data-dictionary": {
        "vi": "từ điển dữ liệu trong workbook",
        "en": "the data dictionary in the workbook",
    },
    "semantic-source.inferred": {
        "vi": "suy luận từ tên cột và giá trị",
        "en": "inferred from the column name and its values",
    },
    "year-column-pairs": {
        "vi": "Hai cột cùng đo một chỉ số ở {first} và {last}.",
        "en": "Two columns measuring the same indicator in {first} and {last}.",
    },

    # --- long tables: why this is one, and which slice to pin --------------
    "longform.is-a-long-table": {
        "vi": "Chỉ có một cột số ({column}) nhưng trung bình {per_place} dòng cho mỗi đơn "
              "vị địa lý, và {categories} cột phân loại đi kèm. Mỗi dòng là một quan sát, "
              "không phải một địa bàn.",
        "en": {
            ONE: "There is a single numeric column ({column}) but an average of {per_place} "
                 "rows per geographic unit, alongside {categories} categorical column. A row "
                 "here is one observation, not one place.",
            "many": "There is a single numeric column ({column}) but an average of "
                     "{per_place} rows per geographic unit, alongside {categories} "
                     "categorical columns. A row here is one observation, not one place.",
        },
    },
    "longform.totals-and-detail-together": {
        "vi": "cột này vừa có dòng tổng ({totals}) vừa có dòng chi tiết",
        "en": "this column holds both total rows ({totals}) and detail rows",
    },
    "longform.needs-pinning": {
        "vi": "{count} cột còn khiến một đơn vị xuất hiện trên nhiều dòng: {columns}. Cộng "
              "thẳng sẽ đếm trùng ở {split}/{places} đơn vị. Ghăm từng cột bằng --where, "
              "hoặc xác nhận rằng các dòng đó là những phần rời nhau của cùng một tổng nên "
              "cộng lại đúng là điều bạn muốn.",
        "en": {
            ONE: "{count} column still puts one unit on several rows: {columns}. A plain sum "
                 "would double-count {split} of {places} units. Pin it with --where, or "
                 "confirm that those rows are disjoint parts of one total and that adding "
                 "them is what you intend.",
            "many": "{count} columns still put one unit on several rows: {columns}. A plain "
                     "sum would double-count {split} of {places} units. Pin each column with "
                     "--where, or confirm that those rows are disjoint parts of one total and "
                     "that adding them is what you intend.",
        },
    },
    "longform.only-one-value": {
        "vi": "chỉ có một giá trị nên không phải chọn",
        "en": "there is only one value, so there is nothing to choose",
    },
    "longform.is-a-total-row": {
        "vi": "là dòng tổng do chính nguồn số liệu cộng sẵn, phủ {units} đơn vị",
        "en": "it is the total row the source itself computed, covering {units} units",
    },
    "longform.covers-the-most-units": {
        "vi": "phủ nhiều đơn vị nhất ({units})",
        "en": "it covers the most units ({units})",
    },
    "longform.latest-period": {
        "vi": "kỳ mới nhất trong {count} kỳ; cộng nhiều kỳ sẽ đếm lặp cùng một người qua "
              "từng kỳ báo cáo",
        "en": "the most recent of {count} periods; summing periods counts the same person "
              "once per reporting period",
    },
    "error.no-mappable-variable": {
        "vi": "Không biến nào trong --layer vẽ được: ",
        "en": "None of the --layer variables can be mapped: ",
    },

    # --- what a column was taken to mean, shown in every profile summary ---
    "semantic.time": {"vi": "kỳ/thời điểm", "en": "period or date"},
    "semantic.identifier": {"vi": "mã định danh", "en": "identifier"},
    "semantic.category": {"vi": "nhóm/phân loại", "en": "category"},
    "semantic.text": {"vi": "văn bản tự do", "en": "free text"},
    "semantic.longitude": {"vi": "kinh độ", "en": "longitude"},
    "semantic.latitude": {"vi": "vĩ độ", "en": "latitude"},
    "semantic.percentage-point": {"vi": "điểm phần trăm", "en": "percentage point"},
    "semantic.percent": {"vi": "phần trăm", "en": "per cent"},
    "semantic.score": {"vi": "chỉ số", "en": "index or score"},
    "semantic.count": {"vi": "số đếm", "en": "count"},
    "semantic.continuous": {"vi": "giá trị liên tục", "en": "continuous value"},
    "semantic.rate": {"vi": "tỷ suất", "en": "rate"},
    "semantic.per-capita": {"vi": "trên {per} dân", "en": "per {per} population"},

    # --- the two channels, as a reader sees them --------------------------
    "channel.name-of.fill": {"vi": "màu vùng", "en": "area fill"},
    "channel.name-of.circles": {"vi": "vòng tròn", "en": "circles"},

    # --- scope of the finished map, shown in the plan ----------------------
    "scope.national": {"vi": "toàn quốc", "en": "national"},
    "scope.with-data": {
        "vi": "các đơn vị có số liệu",
        "en": "the units that have data",
    },

    # --- how the sheet had to be read, relayed with the data summary -------
    "read.header-row": {
        "vi": "Tiêu đề cột nằm ở dòng {row}, không phải dòng 1; {skipped} dòng phía trên "
              "đã được bỏ qua.",
        "en": "The header sits on row {row}, not row 1; the {skipped} rows above it were "
              "skipped.",
    },
    "read.pasted-table": {
        "vi": "Đọc bằng bảng mã {encoding}, dấu phân cách {delimiter}. Bảng dán không mang "
              "kiểu dữ liệu, nên mọi cột được đọc thành chữ rồi mới đổi sang số.",
        "en": "Read as {encoding} with {delimiter} as the delimiter. A pasted table carries "
              "no types, so every column is read as text and then converted to numbers.",
    },
    "read.merged-cells": {
        "vi": "Sheet có {regions} vùng ô gộp. Giá trị của ô gộp đã được điền cho mọi dòng nó "
              "bao phủ{header}.",
        "en": "The sheet has {regions} merged regions. Each merged value was filled down "
              "across every row it covers{header}.",
    },
    "read.merged-header-cells": {
        "vi": "; tiêu đề {levels} tầng đã được ghép thành một tên cột, ví dụ '{example}'",
        "en": "; the {levels}-level header was joined into single column names, for example "
              "'{example}'",
    },
    "read.merged-cells-large-file": {
        "vi": "Sheet có dấu hiệu ô gộp nhưng tệp lớn hơn {limit} MB nên không đọc lại; tên "
              "cột và cột địa danh có thể thiếu.",
        "en": "The sheet shows signs of merged cells, but the file is over {limit} MB so it "
              "was not re-read; column names and the place column may be incomplete.",
    },
    "read.several-tables": {
        "vi": "Sheet chứa {count} bảng tách rời nhau. Đọc thẳng sẽ gộp chúng làm một, và nửa "
              "dưới sẽ mang tên cột của nửa trên. Chọn một bảng, hoặc tách sheet trước.",
        "en": "The sheet holds {count} separate tables. Read straight through they merge into "
              "one, and the lower half inherits the upper half's column names. Pick one "
              "table, or split the sheet first.",
    },
    "read.sampled-only": {
        "vi": "Chỉ đọc {rows} dòng đầu mỗi sheet để trả lời nhanh; chạy profile trên sheet đã "
              "chọn để có hồ sơ đầy đủ.",
        "en": "Only the first {rows} rows of each sheet were read, to answer quickly; run "
              "profile on the chosen sheet for the full picture.",
    },
    "read.duplicate-file": {
        "vi": "Tệp trùng tên và trùng nội dung với tệp đã có trong input/, nên dùng lại tệp đó.",
        "en": "A file of the same name and the same contents is already in input/, so that "
              "one is reused.",
    },
    "read.shared-classes-over-time": {
        "vi": "Dùng chung một cách chia nhóm cho toàn bộ video, nên cùng một màu luôn mang "
              "cùng một ý nghĩa qua các kỳ.",
        "en": "One set of class breaks is shared by the whole animation, so a given colour "
              "means the same thing in every frame.",
    },

    # --- survey verdicts, read aloud when choosing a file ------------------
    "survey.has-a-mappable-sheet": {
        "vi": "{total} workbook, {files} file có sheet vẽ được.",
        "en": "{total} workbooks, {files} of them with a sheet that can be mapped.",
    },
    "survey.unreadable": {
        "vi": "không đọc được workbook.",
        "en": "the workbook could not be read.",
    },
    "survey.no-sheet-at-all": {
        "vi": "{sheets} sheet, không sheet nào vẽ được.",
        "en": "{sheets} sheets, none of which can be mapped.",
    },
    "survey.mappable-sheet": {
        "vi": "{sheets} sheet, {usable} vẽ được: {names}",
        "en": "{sheets} sheets, {usable} of them mappable: {names}",
    },
    "survey.no-workbook": {
        "vi": "Thư mục input/ không có workbook nào.",
        "en": "There is no workbook in the input/ folder.",
    },

    # --- the plan table, in words a reader already has --------------------
    # The command line speaks in flag values — ``choropleth-symbol``,
    # ``weighted-mean``, ``quantile``. A real Codex run put those straight into
    # the table it showed a public-health officer, which is a table nobody
    # outside GIS can agree to. Every enumerated value therefore has a name and
    # one sentence on what choosing it does; :mod:`wording` builds both the row
    # and the menu of alternatives out of these, so the sentence the reader
    # weighs a choice by is the same one the picker shows.
    "field.data": {"vi": "Dữ liệu", "en": "Data"},
    "field.data-slice": {"vi": "Lát dữ liệu", "en": "Data slice"},
    "field.map-kind": {"vi": "Loại bản đồ", "en": "Kind of map"},
    "field.coloured-by": {"vi": "Tô màu theo", "en": "Coloured by"},
    "field.circles-by": {"vi": "Vòng tròn theo", "en": "Circle size by"},
    # not "Coverage": half the tables this skill draws have a column called
    # coverage rate, and a row heading that collides with the data is a heading
    # that will be misread
    "field.scope": {"vi": "Phạm vi bản đồ", "en": "Area the map covers"},
    "field.layout": {"vi": "Bố cục", "en": "Layout"},
    "field.language": {"vi": "Ngôn ngữ bản đồ", "en": "Map language"},
    "field.classes": {"vi": "Chia nhóm màu", "en": "Colour classes"},
    "field.labels": {"vi": "Nhãn trên bản đồ", "en": "Labels on the map"},
    "field.repeated-rows": {"vi": "Gộp dòng trùng", "en": "Repeated rows"},
    "field.output": {"vi": "Đầu ra", "en": "Output"},

    "table.chosen-by-the-skill": {"vi": "[skill tự chọn]", "en": "[chosen by the skill]"},
    "table.current": {"vi": "đang chọn", "en": "current"},
    "table.row-count": {
        "vi": "{rows} dòng",
        "en": {ONE: "{rows} row", "many": "{rows} rows"},
    },
    "table.plate-count": {
        "vi": "{maps} tấm",
        "en": {ONE: "{maps} map", "many": "{maps} maps"},
    },
    "table.class-count": {
        "vi": "{classes} nhóm",
        "en": {ONE: "{classes} class", "many": "{classes} classes"},
    },
    "table.not-applicable": {"vi": "không áp dụng", "en": "not applicable"},
    "table.with-html": {
        "vi": " kèm trang HTML tương tác",
        "en": " plus an interactive HTML page",
    },

    # --- the gate's own instructions to the agent -------------------------
    # These were Vietnamese whatever the conversation was, on the reasoning that
    # the agent reads them and the person does not. Measured, that was 957
    # characters of Vietnamese prose — the longest block in the whole reply —
    # landing in front of an agent one step before it wrote to an English
    # speaker. It answered in Vietnamese. The boundary drawn in decision 27 holds
    # for argparse help and command-syntax errors, which are short and
    # mechanical; a paragraph read immediately before composing a message is a
    # different thing, and it follows the conversation.
    "gate.how-to-present": {
        "vi": "CHƯA VẼ GÌ CẢ. Trình bày bảng 'settings' cho người dùng dưới dạng "
              "danh sách đánh số, nêu rõ những mục có 'note' là skill tự chọn. "
              "Mọi câu hỏi — các mục trong 'must_ask', và bất kỳ dòng nào có "
              "'choices' mà người dùng muốn đổi — phải hỏi bằng GIAO DIỆN LỰA "
              "CHỌN của môi trường (trên Codex là công cụ request_user_input), "
              "truyền nguyên 'question' làm câu hỏi và mỗi phần tử 'choices' làm "
              "một phương án: 'labels' làm nhãn, 'description' làm mô tả, phần tử có "
              "recommended=true đặt lên đầu và ghi thêm '(Recommended)'. Không tự "
              "nghĩ thêm phương án, không hỏi bằng đoạn văn tự do, không đọc tên "
              "cờ hay giá trị cờ ra cho người dùng. Nếu môi trường không có giao "
              "diện lựa chọn thì trình bày cùng nội dung đó bằng bảng Markdown. "
              "Hỏi xong thì DỪNG LẠI CHỜ TRẢ LỜI.",
        "en": "NOTHING HAS BEEN DRAWN. Show the person the 'settings' table as a "
              "numbered list, marking the rows whose 'note' says the skill "
              "chose them. Every question — the entries in 'must_ask', and any "
              "row with 'choices' that the person wants changed — must be asked "
              "through the host's OPTION PICKER (on Codex, the request_user_input "
              "tool), passing 'question' through as the question and each entry of "
              "'choices' as one option: 'labels' as the label, 'description' as the "
              "description, the entry with recommended=true first and marked "
              "'(Recommended)'. Do not invent further options, do not ask in free "
              "prose, and do not read a flag name or a flag value out to the "
              "person. Where the host has no picker, present the same content as "
              "a Markdown table. Having asked, STOP AND WAIT FOR AN ANSWER.",
    },
    "gate.not-yet-asked": {
        "vi": " KHÔNG có mã nào dùng được cho tới khi mọi mục trong 'must_ask' "
              "được hỏi và câu trả lời truyền vào bằng cờ tương ứng. Hỏi trước, "
              "rồi chạy lại lệnh kèm câu trả lời để nhận mã.",
        "en": " NO code exists until every entry in 'must_ask' has been asked and "
              "the answers passed back on the command line. Ask first, then run "
              "the command again with the answers to receive a code.",
    },
    "gate.once-agreed": {
        "vi": " Khi người dùng đồng ý, chạy lại đúng lệnh này kèm --confirmed {code}.",
        "en": " Once the person agrees, run this same command again with "
              "--confirmed {code}.",
    },
    "gate.settings-changed": {
        "vi": " Nếu người dùng đổi bất kỳ mục nào, chạy lại lệnh với thiết lập mới "
              "để lấy mã mới và trình bày lại bảng — mã cũ sẽ không còn dùng được.",
        "en": " If the person changes anything, run the command again with the new "
              "settings to get a new code and show the table again — the old code "
              "stops working.",
    },
    # Emitted in BOTH languages at once, not in the chosen one. It only appears
    # when nobody stated --messages, which is exactly the case where the
    # engine's idea of the conversation language cannot be trusted — so the
    # sentence that says so has to be readable either way.
    "gate.language-not-stated": {
        "vi": " Lệnh này không nêu --messages, nên mọi câu trên đang ở tiếng Việt "
              "theo mặc định. Nếu người dùng đang viết bằng tiếng Anh, chạy lại "
              "kèm --messages en.",
        "en": " This command did not state --messages, so the sentences above are "
              "in Vietnamese by default. If the person is writing in English, run "
              "again with --messages en.",
    },

    "choice.file.question": {
        "vi": "Vẽ bản đồ từ bảng số liệu nào?",
        "en": "Which table should the map be drawn from?",
    },
    "choice.file.description": {
        "vi": "Sheet '{sheet}', {rows}, số liệu ở cấp {level}.",
        "en": "Sheet '{sheet}', {rows}, data at {level} level.",
    },
    "choice.file.upload.label": {
        "vi": "Không phải tệp nào ở trên — tôi sẽ gửi tệp khác",
        "en": "None of these — I will send another file",
    },
    "choice.file.upload.description": {
        "vi": "Đính kèm tệp Excel hoặc CSV của bạn vào cuộc trò chuyện, hoặc dán "
              "thẳng bảng số liệu vào.",
        "en": "Attach your own Excel or CSV file to the conversation, or paste "
              "the table in directly.",
    },

    "choice.map_type.question": {
        "vi": "Vẽ theo kiểu bản đồ nào?",
        "en": "Which kind of map?",
    },
    "choice.map_type.choropleth.label": {
        "vi": "Tô màu vùng theo mức độ",
        "en": "Areas shaded by level",
    },
    "choice.map_type.choropleth.description": {
        "vi": "Mỗi tỉnh hoặc xã mang một sắc độ đậm nhạt theo con số của nó. Đọc "
              "được nơi cao nơi thấp, không đọc được quy mô.",
        "en": "Each province or commune takes a shade set by its own figure. It "
              "shows where the level is high or low, not how large the place is.",
    },
    "choice.map_type.choropleth-symbol.label": {
        "vi": "Tô màu vùng kèm vòng tròn",
        "en": "Shaded areas with circles",
    },
    "choice.map_type.choropleth-symbol.description": {
        "vi": "Màu nền cho biết mức độ, vòng tròn phía trên cho biết số lượng — "
              "hai con số trên cùng một tấm.",
        "en": "The fill carries the level and the circles on top carry the "
              "quantity — two figures on one sheet.",
    },
    "choice.map_type.graduated-symbol.label": {
        "vi": "Vòng tròn to nhỏ theo số lượng",
        "en": "Circles sized by quantity",
    },
    "choice.map_type.graduated-symbol.description": {
        "vi": "Nền để trắng, chỉ có vòng tròn. Hợp với số đếm, vì tô màu vùng "
              "theo số đếm sẽ thành vẽ diện tích và dân số.",
        "en": "The base stays white and only circles are drawn. This suits "
              "counts: shading areas by a count maps area and population instead.",
    },
    "choice.map_type.categorized.label": {
        "vi": "Tô màu theo nhóm",
        "en": "Areas coloured by category",
    },
    "choice.map_type.categorized.description": {
        "vi": "Mỗi nhóm một màu riêng, không có thứ tự đậm nhạt. Dùng cho dữ "
              "liệu phân loại chứ không phải con số đo được.",
        "en": "Each category takes its own colour, with no light-to-dark order. "
              "For classifications rather than measured quantities.",
    },
    "choice.map_type.boundary.label": {
        "vi": "Chỉ vẽ ranh giới",
        "en": "Boundaries only",
    },
    "choice.map_type.boundary.description": {
        "vi": "Bản đồ nền không mang số liệu, dùng để tham chiếu vị trí.",
        "en": "A base map carrying no data, for locating places.",
    },
    "choice.map_type.change.label": {
        "vi": "Bản đồ mức thay đổi",
        "en": "Change map",
    },
    "choice.map_type.change.description": {
        "vi": "Thang màu hai chiều neo tại 0: một phía cho nơi tăng, một phía "
              "cho nơi giảm, màu trung tính đúng nghĩa là không đổi.",
        "en": "A diverging scale anchored at 0: one side for rises, the other "
              "for falls, the neutral colour meaning exactly no change.",
    },
    "choice.map_type.point.label": {
        "vi": "Chấm điểm theo toạ độ",
        "en": "Points at their coordinates",
    },
    "choice.map_type.point.description": {
        "vi": "Mỗi dòng thành một chấm đặt đúng kinh độ và vĩ độ, thay vì tô cả "
              "đơn vị hành chính.",
        "en": "Each row becomes a dot at its own longitude and latitude, instead "
              "of filling a whole administrative unit.",
    },

    "choice.classification.question": {
        "vi": "Chia nhóm màu theo cách nào?",
        "en": "How should the colour classes be cut?",
    },
    "choice.classification.quantile.label": {
        "vi": "Mỗi nhóm có số đơn vị bằng nhau",
        "en": "Equal number of units per class",
    },
    "choice.classification.quantile.description": {
        "vi": "Số đơn vị trong mỗi nhóm màu là như nhau, nên bản đồ luôn dùng "
              "hết dải màu kể cả khi các con số sát nhau.",
        "en": "Every class holds the same number of units, so the map always "
              "uses its full range of shades even when the figures sit close "
              "together.",
    },
    "choice.classification.natural-breaks.label": {
        "vi": "Cắt tại chỗ số liệu tự tách ra",
        "en": "Breaks where the data separates",
    },
    "choice.classification.natural-breaks.description": {
        "vi": "Ranh giới đặt vào những khoảng trống có sẵn trong dãy số liệu, "
              "nên nhóm bám đúng cấu trúc số liệu; đổi lại ranh giới là số lẻ.",
        "en": "The breaks fall in the gaps already present in the figures, so "
              "the classes follow the data's own structure — at the cost of "
              "untidy boundary values.",
    },
    "choice.classification.equal-interval.label": {
        "vi": "Mỗi nhóm có khoảng giá trị bằng nhau",
        "en": "Equal value range per class",
    },
    "choice.classification.equal-interval.description": {
        "vi": "Ranh giới rơi vào số tròn dễ nêu trong báo cáo, nhưng nếu số "
              "liệu chụm lại thì sẽ có nhóm không có đơn vị nào.",
        "en": "The breaks fall on round numbers that are easy to quote in a "
              "report, but classes end up empty when the figures cluster.",
    },

    "choice.labels.question": {
        "vi": "Ghi nhãn gì lên bản đồ?",
        "en": "What should be written on the map?",
    },
    "choice.labels.both.label": {
        "vi": "Ghi cả tên và con số",
        "en": "Both name and figure",
    },
    "choice.labels.both.description": {
        "vi": "Đầy đủ nhất; bản đồ nhiều đơn vị nhỏ thì chỉ những đơn vị đủ chỗ "
              "mới được ghi.",
        "en": "The most complete; on a map of many small units only those with "
              "room get a label.",
    },
    "choice.labels.names.label": {
        "vi": "Chỉ ghi tên đơn vị",
        "en": "Place names only",
    },
    "choice.labels.names.description": {
        "vi": "Người xem biết đang nói tới đâu mà bản đồ không rối, hợp khi con "
              "số đã nằm trong chú giải.",
        "en": "Tells the reader where they are without crowding the map, when "
              "the figures are already in the legend.",
    },
    "choice.labels.values.label": {
        "vi": "Chỉ ghi con số",
        "en": "Figures only",
    },
    "choice.labels.values.description": {
        "vi": "Hợp khi người xem đã thuộc địa bàn và chỉ cần tra số.",
        "en": "For readers who already know the area and just need the numbers.",
    },
    "choice.labels.off.label": {
        "vi": "Không ghi chữ lên bản đồ",
        "en": "No labels on the map",
    },
    "choice.labels.off.description": {
        "vi": "Bản đồ sạch nhất; tên và số tra qua chú giải và trang HTML tương tác.",
        "en": "The cleanest map; names and figures come from the legend and the "
              "interactive page.",
    },

    "choice.layout.question": {
        "vi": "Dùng bố cục nào?",
        "en": "Which layout?",
    },
    "choice.layout.report.label": {
        "vi": "Bố cục báo cáo — chú giải ở cột bên trái",
        "en": "Report layout — legend in a left column",
    },
    "choice.layout.report.description": {
        "vi": "Hợp với tài liệu in và báo cáo khổ A4; bản đồ chiếm phần lớn khung hình.",
        "en": "Suits printed documents and A4 reports; the map takes most of the frame.",
    },
    "choice.layout.banner.label": {
        "vi": "Bố cục dải xanh — tiêu đề đặt trên dải màu",
        "en": "Title across a solid colour band",
    },
    "choice.layout.banner.description": {
        "vi": "Hợp với slide trình chiếu và bản in treo tường; tiêu đề nổi hơn, "
              "chỗ dành cho chú giải hẹp hơn.",
        "en": "Suits slides and wall prints; the title carries further and the "
              "legend has less room.",
    },

    "choice.language.question": {
        "vi": "Chữ trên bản đồ in bằng tiếng gì?",
        "en": "Which language should be printed on the map?",
    },
    "choice.language.vi.label": {"vi": "Tiếng Việt", "en": "Vietnamese"},
    "choice.language.vi.description": {
        "vi": "Chú giải, tiêu đề, thanh tỷ lệ và ghi chú bằng tiếng Việt; hàng "
              "nghìn ngăn bằng dấu chấm (35.156), thập phân bằng dấu phẩy (99,7).",
        "en": "Legend, title, scale bar and notes in Vietnamese; thousands "
              "separated with a full stop (35.156) and decimals with a comma (99,7).",
    },
    "choice.language.en.label": {"vi": "Tiếng Anh", "en": "English"},
    "choice.language.en.description": {
        "vi": "Chú giải, tiêu đề, thanh tỷ lệ và ghi chú bằng tiếng Anh; hàng "
              "nghìn ngăn bằng dấu phẩy (35,156), thập phân bằng dấu chấm (99.7). "
              "Tên địa danh vẫn giữ nguyên tiếng Việt.",
        "en": "Legend, title, scale bar and notes in English; thousands "
              "separated with a comma (35,156) and decimals with a full stop "
              "(99.7). Place names stay in Vietnamese.",
    },

    "choice.formats.question": {
        "vi": "Xuất ảnh ở định dạng nào?",
        "en": "In which image format?",
    },
    "choice.formats.png.label": {"vi": "Ảnh PNG", "en": "PNG image"},
    "choice.formats.png.description": {
        "vi": "Mở được ở mọi máy, dán thẳng vào Word hay PowerPoint.",
        "en": "Opens anywhere and pastes straight into Word or PowerPoint.",
    },
    "choice.formats.svg.label": {"vi": "Ảnh vector SVG", "en": "SVG vector image"},
    "choice.formats.svg.description": {
        "vi": "Phóng to bao nhiêu cũng không vỡ nét, nhưng máy nào thiếu hai "
              "font đóng gói sẽ hiện sai chữ.",
        "en": "Stays sharp at any magnification, but any machine without the "
              "packaged fonts renders the lettering wrongly.",
    },
    "choice.formats.both.label": {"vi": "Cả PNG lẫn SVG", "en": "Both PNG and SVG"},
    "choice.formats.both.description": {
        "vi": "Dùng PNG để gửi đi, giữ SVG để in khổ lớn.",
        "en": "PNG to send around, SVG kept for large-format printing.",
    },

    "choice.map_scope.question": {
        "vi": "Vẽ thành mấy tấm, phạm vi nào?",
        "en": "How many maps, covering what?",
    },
    "choice.map_scope.auto.label": {
        "vi": "Tự chọn theo phạm vi số liệu",
        "en": "Chosen from the reach of the data",
    },
    "choice.map_scope.auto.description": {
        "vi": "Số liệu phủ nhiều tỉnh thì vẽ toàn quốc, chỉ nằm trong một tỉnh "
              "thì vẽ riêng tỉnh đó.",
        "en": "Data spanning many provinces gets a national map; data inside one "
              "province gets that province alone.",
    },
    "choice.map_scope.national.label": {"vi": "Một tấm toàn quốc", "en": "One national map"},
    "choice.map_scope.national.description": {
        # Named no islands: this sentence is shown for whichever country is
        # being drawn, and it used to offer Vietnam's to all of them.
        "vi": "Cả nước trên một tấm; lãnh thổ ngoài khơi đã khai nằm trong khung phụ.",
        "en": "The whole country on one sheet; declared offshore territory goes "
              "in an inset.",
    },
    "choice.map_scope.single-province.label": {
        "vi": "Một tấm cho một tỉnh",
        "en": "One map of a single province",
    },
    "choice.map_scope.single-province.description": {
        "vi": "Chỉ vẽ tỉnh đang xét, kèm bản đồ định vị nhỏ cho biết tỉnh đó nằm đâu.",
        "en": "Just the province in question, with a small locator showing where "
              "it sits.",
    },
    "choice.map_scope.province-series.label": {
        "vi": "Mỗi tỉnh một tấm riêng",
        "en": "One map per province",
    },
    "choice.map_scope.province-series.description": {
        "vi": "Một loạt bản đồ dùng chung thang màu, nên so sánh được giữa các tỉnh.",
        "en": "A series sharing one colour scale, so the provinces stay comparable.",
    },
    "choice.map_scope.matched-only.label": {
        "vi": "Chỉ vẽ các đơn vị có số liệu",
        "en": "Only the units that have data",
    },
    "choice.map_scope.matched-only.description": {
        "vi": "Đơn vị không có số liệu biến mất hẳn, nên bức tranh trông như cả "
              "nước chỉ gồm ngần ấy đơn vị. Chỉ dùng khi người dùng yêu cầu rõ.",
        "en": "Units without data disappear altogether, so the picture reads as "
              "a country made up of just those units. Use only when the reader "
              "has asked for it.",
    },

    "choice.aggregate.question": {
        "vi": "Một đơn vị nằm trên nhiều dòng thì gộp lại bằng cách nào?",
        "en": "When a unit spans several rows, how should they be combined?",
    },
    "choice.aggregate.auto.label": {
        "vi": "Tự chọn theo loại số liệu",
        "en": "Chosen from the kind of figure",
    },
    "choice.aggregate.auto.description": {
        "vi": "Số đếm thì cộng lại, tỷ lệ thì lấy trung bình có trọng số.",
        "en": "Counts are added; rates are averaged with weights.",
    },
    "choice.aggregate.sum.label": {"vi": "Cộng dồn", "en": "Add together"},
    "choice.aggregate.sum.description": {
        "vi": "Đúng với số đếm; cộng hai tỷ lệ với nhau thì không ra tỷ lệ nào có nghĩa.",
        "en": "Right for counts; adding two rates does not produce a rate.",
    },
    "choice.aggregate.mean.label": {"vi": "Trung bình đơn giản", "en": "Plain average"},
    "choice.aggregate.mean.description": {
        "vi": "Mọi dòng tính ngang nhau, nên một xã 2.000 dân nặng bằng một xã "
              "100.000 dân.",
        "en": "Every row counts the same, so a commune of 2,000 weighs as much "
              "as one of 100,000.",
    },
    "choice.aggregate.weighted-mean.label": {
        "vi": "Trung bình có trọng số",
        "en": "Weighted average",
    },
    "choice.aggregate.weighted-mean.description": {
        "vi": "Lấy trung bình theo dân số hoặc mẫu số, nên đơn vị đông dân ảnh "
              "hưởng đúng phần của nó.",
        "en": "Averaged by population or by the denominator, so a populous unit "
              "carries its proper share.",
    },
    "choice.aggregate.median.label": {"vi": "Lấy trung vị", "en": "Take the median"},
    "choice.aggregate.median.description": {
        "vi": "Giá trị nằm giữa; một dòng bất thường không kéo lệch được.",
        "en": "The middle value; one unusual row cannot drag it.",
    },
    "choice.aggregate.max.label": {"vi": "Lấy giá trị lớn nhất", "en": "Take the largest"},
    "choice.aggregate.max.description": {
        "vi": "Chỉ giữ dòng cao nhất của mỗi đơn vị, dùng cho ngưỡng cảnh báo.",
        "en": "Keeps only each unit's highest row, for thresholds and alerts.",
    },
    "choice.aggregate.min.label": {"vi": "Lấy giá trị nhỏ nhất", "en": "Take the smallest"},
    "choice.aggregate.min.description": {
        "vi": "Chỉ giữ dòng thấp nhất của mỗi đơn vị.",
        "en": "Keeps only each unit's lowest row.",
    },
    "choice.aggregate.mode.label": {
        "vi": "Lấy giá trị hay gặp nhất",
        "en": "Take the most frequent value",
    },
    "choice.aggregate.mode.description": {
        "vi": "Dùng cho cột phân loại, nơi cộng hay lấy trung bình đều vô nghĩa.",
        "en": "For classification columns, where adding or averaging means nothing.",
    },
    "choice.aggregate.first.label": {"vi": "Lấy dòng đầu tiên", "en": "Take the first row"},
    "choice.aggregate.first.description": {
        "vi": "Chỉ đúng khi mọi dòng của một đơn vị vốn mang cùng một giá trị.",
        "en": "Only correct when every row of a unit already carries the same value.",
    },

    # --- hard stops the user has to act on --------------------------------
    # --- stops written where they happen ---------------------------------
    # These 32 sentences used to sit in the modules that raise them, which meant
    # --messages en answered every one of them in Vietnamese. A stop is the
    # message a person is most likely to read, so it is the last place to leave
    # untranslated.
    "error.place-column-required": {
        "vi": "Cần {flag} để biết cột nào chứa địa danh cấp {level}. "
              "Chạy 'profile' trước để engine đề xuất cột.",
        "en": "{flag} is needed to say which column holds the {level} place names. "
              "Run 'profile' first and the engine will suggest one.",
    },
    "error.workbook-not-found": {
        "vi": "Không tìm thấy workbook: {file}",
        "en": "No such workbook: {file}",
    },
    "error.where-unknown-column": {
        "vi": "--where trỏ vào cột không có: {column}. Các cột hiện có: {available}",
        "en": "--where names a column that is not there: {column}. Columns present: {available}",
    },
    "error.where-no-rows": {
        "vi": "--where '{column}={value}' không khớp dòng nào. Giá trị đang có: {near}",
        "en": "--where '{column}={value}' matches no rows. Values present: {near}",
    },
    "error.where-empty-result": {
        "vi": "Sau khi lọc --where không còn dòng nào.",
        "en": "The --where filters leave no rows.",
    },
    "error.where-bad-format": {
        "vi": "--where cần dạng CỘT=GIÁ_TRỊ, nhận được: {given}",
        "en": "--where takes COLUMN=VALUE; received: {given}",
    },
    "error.where-missing-column": {
        "vi": "--where thiếu tên cột: {given}",
        "en": "--where has no column name: {given}",
    },
    "error.layer-unknown-column": {
        "vi": "--layer trỏ vào cột không có: {column}. Các cột hiện có: {available}",
        "en": "--layer names a column that is not there: {column}. Columns present: {available}",
    },
    "error.layer-value-not-in-column": {
        "vi": "--layer '{value}' không có trong cột {column}. Giá trị gần đúng: {near}",
        "en": "--layer '{value}' does not appear in column {column}. Nearest values: {near}",
    },
    "error.layer-slice-unknown-column": {
        "vi": "Lát của --layer '{layer}' trỏ vào cột không có: {column}",
        "en": "The slice on --layer '{layer}' names a column that is not there: {column}",
    },
    "error.indicator-column-unknown": {
        "vi": "--indicator-column trỏ vào cột không có: {column}. Các cột hiện có: {available}",
        "en": "--indicator-column names a column that is not there: {column}. "
              "Columns present: {available}",
    },
    "error.indicator-column-required": {
        "vi": "Cần --indicator-column (hoặc --ratio-column) để biết cột nào chứa tên chỉ số.",
        "en": "--indicator-column (or --ratio-column) is needed to say which column "
              "holds the indicator names.",
    },
    "error.long-table-needs-value-column": {
        "vi": "Bảng dạng dài cần --value-column trỏ vào cột chứa số.",
        "en": "A long table needs --value-column pointing at the column of numbers.",
    },
    "error.no-rows-for-indicator": {
        "vi": "Không có dòng nào cho {label} '{value}'. Giá trị đang có: {near}",
        "en": "No rows for the {label} '{value}'. Values present: {near}",
    },
    "error.slice-unknown-column": {
        "vi": "Lát của '{indicator}' trỏ vào cột không có: {column}",
        "en": "The slice on '{indicator}' names a column that is not there: {column}",
    },
    "error.slice-no-rows": {
        "vi": "Lát '{column}={value}' không khớp dòng nào của '{indicator}'. "
              "Giá trị đang có: {near}",
        "en": "The slice '{column}={value}' matches no rows of '{indicator}'. "
              "Values present: {near}",
    },
    "error.ratio-needs-both": {
        "vi": "Chế độ tỷ số cần đủ --numerator và --denominator.",
        "en": "Ratio mode needs both --numerator and --denominator.",
    },
    "error.point-colour-column-unknown": {
        "vi": "--point-color-column trỏ vào cột không có: {column}",
        "en": "--point-color-column names a column that is not there: {column}",
    },
    "error.point-size-column-unknown": {
        "vi": "--point-size-column trỏ vào cột không có: {column}",
        "en": "--point-size-column names a column that is not there: {column}",
    },
    "error.no-unit-with-shape-id": {
        "vi": "Không có đơn vị nào mang shape_id={shape_id}",
        "en": "No unit carries shape_id={shape_id}",
    },
    "error.animation-needs-period-column": {
        "vi": "Bản đồ video cần --period-column để biết đâu là trục thời gian.",
        "en": "A map over time needs --period-column to say which column is the time axis.",
    },
    "error.animation-needs-two-periods": {
        # English inflects around the count and Vietnamese does not, so the
        # singular is a variant here rather than a string built in the caller.
        "vi": "Cột '{column}' chỉ có {count} kỳ; cần ít nhất 2 kỳ để dựng video.",
        "en": {ONE: "Column '{column}' holds only {count} period; at least 2 are "
                    "needed to build a map over time.",
               "many": "Column '{column}' holds only {count} periods; at least 2 "
                       "are needed to build a map over time."},
    },
    "error.no-values-after-periods": {
        "vi": "Không còn giá trị nào sau khi ghép địa danh và tách kỳ.",
        "en": "No values are left once the place names are matched and the periods split.",
    },
    "error.no-rows-matched": {
        "vi": "Không ghép được dòng nào với bản đồ. Xem lại {file}.",
        "en": "No row could be matched to the map. Look at {file}.",
    },
    "error.change-needs-two-columns": {
        "vi": "Bản đồ thay đổi cần cả --baseline-column và --comparison-column.",
        "en": "A change map needs both --baseline-column and --comparison-column.",
    },
    "error.graduated-needs-symbol-column": {
        "vi": "Bản đồ ký hiệu tỷ lệ cần --symbol-column.",
        "en": "A proportional-symbol map needs --symbol-column.",
    },
    "error.needs-value-column": {
        "vi": "Cần --value-column (hoặc --category-column) cho loại bản đồ này.",
        "en": "This kind of map needs --value-column (or --category-column).",
    },
    "error.point-needs-coordinates": {
        "vi": "Bản đồ điểm cần cột kinh độ và vĩ độ. Chỉ định --lon-column và --lat-column.",
        "en": "A point map needs a longitude and a latitude column. "
              "Name them with --lon-column and --lat-column.",
    },
    "error.no-rows-with-coordinates": {
        "vi": "Không có dòng nào có đủ toạ độ trong '{lon}' và '{lat}'.",
        "en": "No row carries both coordinates in '{lon}' and '{lat}'.",
    },
    "error.no-values-after-matching": {
        "vi": "Sau khi ghép địa danh, không còn giá trị nào để vẽ.",
        "en": "Once the place names are matched, no value is left to draw.",
    },
    "error.missing-library": {
        "vi": "Thiếu thư viện {library}. Chạy lại với: uv run --with {library} ...",
        "en": "{library} is not installed. Run again with: uv run --with {library} ...",
    },
    "error.file-not-found": {
        "vi": "Không tìm thấy tệp: {path}",
        "en": "File not found: {path}",
    },
    "error.unreadable-format": {
        "vi": "Định dạng {suffix} không đọc được. Các định dạng nhận được: {accepted}. Nếu "
              "dữ liệu đang nằm trong PDF hoặc ảnh, cần xuất ra Excel/CSV trước.",
        "en": "Cannot read {suffix} files. Accepted formats: {accepted}. If the data is in a "
              "PDF or an image, export it to Excel or CSV first.",
    },
    "error.no-extension": {"vi": "(không có đuôi)", "en": "(no extension)"},
    "error.boundary-folder-missing": {
        "vi": "Không tìm thấy thư mục shapefile: {folder}",
        "en": "Shapefile folder not found: {folder}",
    },
    "error.no-boundary-file": {
        "vi": "Không có tệp ranh giới nào trong {folder}. Các định dạng nhận được: {accepted}",
        "en": "No boundary file in {folder}. Accepted formats: {accepted}",
    },
    "error.several-boundary-files": {
        "vi": "Thư mục {folder} có nhiều tệp ranh giới nên không biết vẽ tệp nào: {files}. "
              "Mỗi thư mục cấp hành chính chỉ được chứa một bộ dữ liệu.",
        "en": "More than one boundary dataset in {folder}, so there is no way to tell which "
              "to draw: {files}. A tier folder holds exactly one dataset.",
    },
    "list.geopandas-missing": {
        "vi": "chưa cài geopandas nên chưa đọc được hồ sơ quốc gia",
        "en": "geopandas is not installed, so the country profile was not read",
    },
    "error.map-text-bad-format": {
        "vi": "--map-text cần dạng KHOÁ=GIÁ TRỊ, nhận được: {item}",
        "en": "--map-text needs KEY=VALUE, and got: {item}",
    },
    "error.map-text-unknown-key": {
        # ``name`` rather than ``key``: ``messages.text`` takes the message's
        # own key as its first argument, and a field of the same name collides
        # with it — silently at the call site and loudly at run time.
        "vi": "--map-text không có khoá '{name}'. Các khoá nhận được: {known}",
        "en": "--map-text has no key '{name}'. Accepted keys: {known}",
    },
    "error.is-a-country-outline": {
        "vi": "Tệp này là đường viền của cả quốc gia, không phải một cấp hành chính "
              "({evidence}). Hãy đặt tệp cấp tỉnh/bang vào thư mục cấp.",
        "en": "This file is the outline of the whole country, not an administrative "
              "tier ({evidence}). Put the province- or state-level file in the tier "
              "folder instead.",
    },
    "error.no-name-column": {
        "vi": "Không tìm được cột tên địa danh cho cấp '{level}'. {evidence}",
        "en": "No place-name column found for the '{level}' tier. {evidence}",
    },
    "error.no-such-country": {
        "vi": "Không có dữ liệu ranh giới cho '{country}'. Đang có: {available}",
        "en": "No boundary data for '{country}'. Available: {available}",
    },
    "error.bad-inset-declaration": {
        "vi": "'{field}' trong {file} phải là kinh độ từ -180 đến 180, hoặc null "
              "nếu quốc gia này không dùng khung phụ. Đang là {given}.",
        "en": "'{field}' in {file} has to be a longitude between -180 and 180, or "
              "null if this country uses no inset. It reads {given}.",
    },
    "error.several-countries": {
        "vi": "Có ranh giới của nhiều quốc gia nên phải nói rõ vẽ nước nào: {available}",
        "en": "Boundaries for more than one country are present, so which to draw has "
              "to be said: {available}",
    },
    "error.no-such-tier": {
        "vi": "Không có cấp '{level}' cho {country}. Các cấp đang có (kèm số đơn vị): "
              "{available}",
        "en": "No '{level}' tier for {country}. Tiers present, with unit counts: "
              "{available}",
    },
    "error.missing-sidecar-file": {
        "vi": "Shapefile {path} thiếu tệp đi kèm: {missing}. Một shapefile không phải một "
              "tệp đơn lẻ; thiếu .shx là mất hình học, thiếu .dbf là mất bảng thuộc tính.",
        "en": "The shapefile {path} is missing companion files: {missing}. A shapefile is not "
              "a single file; without .shx there is no geometry, without .dbf no attributes.",
    },
    "error.missing-font": {
        "vi": "Thiếu font. Dựng lại theo hướng dẫn trong README của thư mục font, "
              "rồi đặt các tệp .ttf vào {folder}. Đang thiếu: {missing}",
        "en": "The packaged fonts are missing. Rebuild them as the README in the font "
              "folder describes and put the .ttf files in {folder}. Missing: {missing}",
    },
    "error.wrong-font-family": {
        "vi": "Font '{family}' có file trong {folder} nhưng matplotlib đọc ra họ khác: "
              "{found}. Thường là do subset làm mất nameID 16 (Typographic Family). Dựng lại "
              "theo assets/fonts/README.md.",
        "en": "Font '{family}' has a file in {folder} but matplotlib reads its family as "
              "{found}. Usually the subsetter dropped nameID 16 (Typographic Family). Rebuild "
              "it following assets/fonts/README.md.",
    },
    "error.no-numeric-value": {
        "vi": "Không có giá trị số nào để phân lớp.",
        "en": "There are no numeric values to classify.",
    },

    # --- animation notes ---------------------------------------------------
    "video.no-room-for-the-timeline": {
        "vi": "Bố cục chưa dành chỗ cho thanh thời gian.",
        "en": "The layout has left no room for the timeline.",
    },
    "video.mp4-through-ffmpeg": {
        "vi": "Xuất MP4 bằng ffmpeg.",
        "en": "Exported as MP4 with ffmpeg.",
    },
    "video.no-ffmpeg": {
        "vi": "Không tìm thấy ffmpeg nên đã xuất GIF; cài ffmpeg để có MP4 nhẹ và nét hơn.",
        "en": "ffmpeg was not found, so a GIF was written instead; install ffmpeg for a "
              "smaller, sharper MP4.",
    },
}


_PLACEHOLDER = re.compile(r"\{(\w+)")


def placeholders(text: str) -> set[str]:
    """The named fields a template expects. Used by the parity test."""
    return set(_PLACEHOLDER.findall(text))


def fragment(key: str, lang: str | None = None, **fmt: Any) -> str:
    return FRAGMENTS[key][normalise(lang)].format(**fmt)


def text(key: str, lang: str | None = None, singular: bool = False,
         **fmt: Any) -> str:
    """One standalone sentence, formatted, in the chosen language.

    ``singular`` selects the ``ONE`` variant where the entry has one.
    """
    entry = TEXT[key][normalise(lang)]
    if isinstance(entry, dict):
        entry = entry[ONE] if singular and ONE in entry else entry["many"]
    return entry.format(**fmt)


def issue(key: str, lang: str | None = None, singular: bool = False,
          **fmt: Any) -> dict[str, str]:
    """The three sentences of one warning, formatted, in the chosen language.

    ``singular`` is set by the caller when the sentence counts exactly one
    thing; entries that need it carry an ``ONE`` block overriding the fields
    that inflect.
    """
    entry = ISSUES[key][normalise(lang)]
    if singular:
        entry = {**entry, **entry.get(ONE, {})}
    return {field: entry[field].format(**fmt) for field in (WHAT, WHY, FIX)}
