"""Joining dataset place names to shapefile features.

The user never supplies administrative codes, so everything downstream rests on
this module. The cases below are the ones that go wrong quietly: an abbreviated
prefix, a missing accent, a typo, and a commune name that exists in more than
one province.
"""

from __future__ import annotations

import unittest

import context  # noqa: F401  (path bootstrap)
from emap import matching


def index_of(*names: str):
    return matching.build_index(
        [{"name": name, "shape_id": i} for i, name in enumerate(names)], matching.VIETNAM)


class TestNormalize(unittest.TestCase):
    def test_strips_accents_and_lowercases(self):
        self.assertEqual(matching.normalize("Minh Châu", matching.VIETNAM), "minh chau")

    def test_strips_d_stroke(self):
        self.assertEqual(matching.normalize("Đan Điền", matching.VIETNAM), "dan dien")

    def test_strips_the_word_prefix(self):
        self.assertEqual(matching.normalize("Xã Minh Châu", matching.VIETNAM), "minh chau")
        self.assertEqual(matching.normalize("Phường Ba Đình", matching.VIETNAM), "ba dinh")
        self.assertEqual(matching.normalize("Thành phố Huế", matching.VIETNAM), "hue")

    def test_strips_abbreviated_prefixes(self):
        """Punctuation is removed first, so 'P.' has to be matched bare."""
        self.assertEqual(matching.normalize("P. Phú Hồ", matching.VIETNAM), "phu ho")
        self.assertEqual(matching.normalize("TT. Khe Tre", matching.VIETNAM), "khe tre")
        self.assertEqual(matching.normalize("TP. Cần Thơ", matching.VIETNAM), "can tho")

    def test_does_not_eat_a_name_that_merely_starts_with_a_prefix_letter(self):
        self.assertEqual(matching.normalize("Phú Hồ", matching.VIETNAM), "phu ho")
        self.assertEqual(matching.normalize("Xuân Mai", matching.VIETNAM), "xuan mai")
        self.assertEqual(matching.normalize("Hòa Bình", matching.VIETNAM), "hoa binh")

    def test_collapses_whitespace_and_punctuation(self):
        """The hyphen goes with the rest of the punctuation.

        It used to survive, which meant "Ba Ria-Vung Tau" and "Bà Rịa - Vũng Tàu"
        reached each other only as a fuzzy guess needing review.
        """
        self.assertEqual(matching.normalize("  Chân  Mây - Lăng Cô ", matching.VIETNAM),
                         "chan may lang co")
        self.assertEqual(matching.normalize("Chân Mây-Lăng Cô", matching.VIETNAM),
                         matching.normalize("Chân Mây - Lăng Cô", matching.VIETNAM))

    def test_empty_input(self):
        self.assertEqual(matching.normalize(None, matching.VIETNAM), "")


class TestMatchOne(unittest.TestCase):
    def setUp(self):
        self.index = index_of("Minh Châu", "Phú Hồ", "Tân Hòa", "Vị Thanh")

    def test_literal_hit_is_reported_as_exact(self):
        feature, score, method = matching.match_one("Minh Châu", self.index)
        self.assertEqual(method, matching.EXACT)
        self.assertEqual(score, 100.0)
        self.assertEqual(feature["name"], "Minh Châu")

    def test_accent_and_prefix_handling_is_reported_as_normalised(self):
        feature, score, method = matching.match_one("Xa Minh Chau", self.index)
        self.assertEqual(method, matching.NORMALISED)
        self.assertEqual(feature["name"], "Minh Châu")

    def test_typo_is_reported_as_fuzzy(self):
        feature, score, method = matching.match_one("Tân Hò", self.index)
        self.assertEqual(method, matching.FUZZY)
        self.assertEqual(feature["name"], "Tân Hòa")
        self.assertLess(score, 100.0)

    def test_unrelated_name_is_left_unmatched(self):
        feature, _, method = matching.match_one("Không Có Ở Đây", self.index)
        self.assertIsNone(feature)
        self.assertEqual(method, matching.NONE)

    def test_blank_name_is_left_unmatched(self):
        self.assertEqual(matching.match_one("   ", self.index)[2], matching.NONE)

    def test_fuzzy_floor_is_respected(self):
        feature, _, method = matching.match_one("Tân Hò", self.index, fuzzy_floor=99.0)
        self.assertIsNone(feature)
        self.assertEqual(method, matching.NONE)


class TestAmbiguity(unittest.TestCase):
    """Hải Phòng really does contain both 'Cẩm Giang' and 'Cẩm Giàng'."""

    def setUp(self):
        self.index = index_of("Cẩm Giang", "Cẩm Giàng", "Vĩnh Bảo")

    def test_accentless_input_is_flagged_not_guessed(self):
        _, _, method = matching.match_one("Cam Giang", self.index)
        self.assertEqual(method, matching.AMBIGUOUS)
        self.assertEqual(matching.status_for(method, 100.0), matching.REVIEW)

    def test_a_fully_written_name_still_resolves_exactly(self):
        feature, _, method = matching.match_one("Cẩm Giàng", self.index)
        self.assertEqual(method, matching.EXACT)
        self.assertEqual(feature["name"], "Cẩm Giàng")

    def test_candidates_are_listed_for_the_reviewer(self):
        self.assertEqual(matching.candidates_for("Cam Giang", self.index),
                         ["Cẩm Giang", "Cẩm Giàng"])

    def test_an_unambiguous_name_is_still_normalised(self):
        _, _, method = matching.match_one("Vinh Bao", self.index)
        self.assertEqual(method, matching.NORMALISED)

    def test_review_record_carries_the_candidates(self):
        provinces = index_of("Hải Phòng")
        communes = {"Hải Phòng": self.index}
        review = matching.review_commune(
            [{"province": "Hải Phòng", "commune": "Cam Giang"}], provinces, communes)
        self.assertEqual(review[0]["match_method"], matching.AMBIGUOUS)
        self.assertEqual(review[0]["status"], matching.REVIEW)
        self.assertIn("Cẩm Giàng", review[0]["candidates"])

    def test_summary_counts_ambiguous_separately_from_fuzzy(self):
        records = [
            {"status": matching.REVIEW, "match_method": matching.AMBIGUOUS},
            {"status": matching.REVIEW, "match_method": matching.FUZZY},
        ]
        summary = matching.summarize(records)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertEqual(summary["fuzzy"], 1)


class TestStatus(unittest.TestCase):
    def test_exact_and_normalised_are_high_confidence(self):
        self.assertEqual(matching.status_for(matching.EXACT, 100.0), matching.HIGH)
        self.assertEqual(matching.status_for(matching.NORMALISED, 100.0), matching.HIGH)

    def test_fuzzy_always_needs_review(self):
        """The previous build marked a 95%-similar guess as high-confidence."""
        self.assertEqual(matching.status_for(matching.FUZZY, 92.3), matching.REVIEW)

    def test_a_weak_province_match_downgrades_a_clean_commune_match(self):
        self.assertEqual(matching.status_for(matching.NORMALISED, 100.0, secondary=70.0),
                         matching.REVIEW)

    def test_unmatched(self):
        self.assertEqual(matching.status_for(matching.NONE, 0.0), matching.UNMATCHED)


class TestReviewProvince(unittest.TestCase):
    def setUp(self):
        self.index = index_of("Hà Nội", "Huế", "Cần Thơ")

    def test_one_record_per_distinct_name_with_row_counts(self):
        rows = [{"province": "Hà Nội"}, {"province": "Hà Nội"}, {"province": "Huế"}]
        review = matching.review_province(rows, self.index)
        self.assertEqual(len(review), 2)
        by_name = {r["dataset_province"]: r for r in review}
        self.assertEqual(by_name["Hà Nội"]["row_count"], 2)
        self.assertEqual(by_name["Huế"]["row_count"], 1)

    def test_unmatched_province_carries_no_shape_id(self):
        review = matching.review_province([{"province": "Tỉnh Không Tồn Tại"}], self.index)
        self.assertEqual(review[0]["status"], matching.UNMATCHED)
        self.assertEqual(review[0]["shape_id"], "")


class TestReviewCommune(unittest.TestCase):
    def setUp(self):
        self.provinces = index_of("Hà Nội", "Cần Thơ")
        # the same commune name deliberately exists in both provinces
        self.communes = {
            "Hà Nội": matching.build_index([
                {"name": "Minh Châu", "shape_id": 101},
                {"name": "Tân Hòa", "shape_id": 102},
            ], matching.VIETNAM),
            "Cần Thơ": matching.build_index([
                {"name": "Tân Hòa", "shape_id": 201},
                {"name": "Vị Thanh", "shape_id": 202},
            ], matching.VIETNAM),
        }

    def review(self, rows):
        return matching.review_commune(rows, self.provinces, self.communes)

    def test_commune_is_resolved_inside_its_own_province(self):
        """A shared name must not leak across provinces."""
        review = self.review([
            {"province": "Hà Nội", "commune": "Tân Hòa"},
            {"province": "Cần Thơ", "commune": "Tân Hòa"},
        ])
        by_province = {r["dataset_province"]: r["shape_id"] for r in review}
        self.assertEqual(by_province["Hà Nội"], 102)
        self.assertEqual(by_province["Cần Thơ"], 201)

    def test_the_three_fixture_typos(self):
        review = self.review([
            {"province": "Hà Nội", "commune": "Xa Minh Chau"},
            {"province": "Cần Thơ", "commune": "Tân Hò"},
        ])
        by_raw = {r["dataset_commune"]: r for r in review}
        self.assertEqual(by_raw["Xa Minh Chau"]["matched_commune"], "Minh Châu")
        self.assertEqual(by_raw["Xa Minh Chau"]["match_method"], matching.NORMALISED)
        self.assertEqual(by_raw["Tân Hò"]["matched_commune"], "Tân Hòa")
        self.assertEqual(by_raw["Tân Hò"]["match_method"], matching.FUZZY)
        self.assertEqual(by_raw["Tân Hò"]["status"], matching.REVIEW)

    def test_unknown_province_blocks_the_commune(self):
        review = self.review([{"province": "Nghệ An", "commune": "Tân Hòa"}])
        self.assertEqual(review[0]["status"], matching.UNMATCHED)
        self.assertEqual(review[0]["shape_id"], "")

    def test_duplicate_pairs_are_counted_once(self):
        review = self.review([
            {"province": "Hà Nội", "commune": "Minh Châu"},
            {"province": "Hà Nội", "commune": "Minh Châu"},
        ])
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["row_count"], 2)

    def test_manual_override_wins_over_matching(self):
        overrides = {"hà nội|Tổ dân phố số 5".lower(): {"shape_id": 101,
                                                        "matched_name": "Minh Châu"}}
        review = matching.review_commune(
            [{"province": "Hà Nội", "commune": "Tổ dân phố số 5"}],
            self.provinces, self.communes, overrides)
        self.assertEqual(review[0]["shape_id"], 101)
        self.assertEqual(review[0]["match_method"], matching.OVERRIDE)
        self.assertEqual(review[0]["status"], matching.HIGH)


class TestSummarize(unittest.TestCase):
    def test_counts_by_status_and_method(self):
        records = [
            {"status": matching.HIGH, "match_method": matching.EXACT},
            {"status": matching.HIGH, "match_method": matching.NORMALISED},
            {"status": matching.REVIEW, "match_method": matching.FUZZY},
            {"status": matching.UNMATCHED, "match_method": matching.NONE},
        ]
        summary = matching.summarize(records)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["high-confidence"], 2)
        self.assertEqual(summary["needs-review"], 1)
        self.assertEqual(summary["unmatched"], 1)
        self.assertEqual(summary["fuzzy"], 1)

    def test_rows_needing_attention_excludes_clean_joins(self):
        records = [
            {"status": matching.HIGH, "dataset_commune": "A"},
            {"status": matching.REVIEW, "dataset_commune": "B"},
            {"status": matching.UNMATCHED, "dataset_commune": "C"},
        ]
        flagged = [r["dataset_commune"] for r in matching.rows_needing_attention(records)]
        self.assertEqual(flagged, ["B", "C"])


if __name__ == "__main__":
    unittest.main()


class TestShapeLookup(unittest.TestCase):
    """What actually reaches the map.

    An ambiguous row keeps its shape id so the review table can show which
    commune would have been picked. Whether that id is allowed to join is a
    separate decision, and the default is no: a guessed unit on a finished map
    looks exactly like a known one.
    """

    def setUp(self):
        provinces = index_of("Hải Phòng")
        communes = {"Hải Phòng": index_of("Cẩm Giang", "Cẩm Giàng", "An Dương")}
        self.review = matching.review_commune(
            [{"province": "Hải Phòng", "commune": "Cam Giang"},
             {"province": "Hải Phòng", "commune": "An Dương"}],
            provinces, communes)

    def test_an_ambiguous_row_is_left_out_by_default(self):
        lookup = matching.shape_lookup(self.review, "commune")
        self.assertNotIn("Hải Phòng|Cam Giang", lookup)

    def test_the_rows_that_are_certain_still_join(self):
        lookup = matching.shape_lookup(self.review, "commune")
        self.assertIn("Hải Phòng|An Dương", lookup)

    def test_keeping_ambiguity_is_possible_but_has_to_be_asked_for(self):
        lookup = matching.shape_lookup(self.review, "commune", drop_ambiguous=False)
        self.assertIn("Hải Phòng|Cam Giang", lookup)

    def test_a_row_that_matched_nothing_never_joins(self):
        review = matching.review_commune(
            [{"province": "Hải Phòng", "commune": "Không Có Thật Ở Đâu Cả"}],
            index_of("Hải Phòng"), {"Hải Phòng": index_of("An Dương")})
        for keep in (True, False):
            self.assertEqual(
                matching.shape_lookup(review, "commune", drop_ambiguous=keep), {})

    def test_province_level_data_is_keyed_by_province_alone(self):
        review = matching.review_province([{"province": "Hải Phòng"}],
                                          index_of("Hải Phòng"))
        self.assertEqual(list(matching.shape_lookup(review, "province")), ["Hải Phòng"])


class TestEnglishLanguageSources(unittest.TestCase):
    """A PEPFAR MER export names places in English, the shapefile in Vietnamese.

    Both defects below were found on a real 70.000-row file: the first one alone
    stranded 35.431 rows — half the dataset — on a single unmatched name.
    """

    def test_the_english_administrative_suffix_is_dropped(self):
        self.assertEqual(matching.normalize("Ho Chi Minh City", matching.VIETNAM),
                         matching.normalize("TP. Hồ Chí Minh", matching.VIETNAM))
        self.assertEqual(matching.normalize("Thai Nguyen Province", matching.VIETNAM),
                         matching.normalize("Thái Nguyên", matching.VIETNAM))

    def test_a_name_that_merely_ends_in_those_letters_is_kept(self):
        self.assertEqual(matching.normalize("Bac City Giang", matching.VIETNAM), "bac city giang")
        self.assertEqual(matching.normalize("Mỹ City", matching.VIETNAM), "my")

    def test_hyphen_spacing_does_not_turn_a_match_into_a_guess(self):
        self.assertEqual(matching.normalize("Ba Ria-Vung Tau", matching.VIETNAM),
                         matching.normalize("Bà Rịa - Vũng Tàu", matching.VIETNAM))

    def test_an_english_name_still_reaches_the_shapefile_feature(self):
        index = index_of("TP. Hồ Chí Minh", "Hải Phòng")
        feature, score, method = matching.match_one("Ho Chi Minh City", index)
        self.assertIsNotNone(feature)
        self.assertEqual(feature["name"], "TP. Hồ Chí Minh")
        self.assertEqual(method, matching.NORMALISED)


class TestAdminLevelSanity(unittest.TestCase):
    """A district column dressed as a commune column.

    Vietnam abolished districts in 2025. A PEPFAR export still reports them, and
    because many districts share a name with a commune the join succeeds often
    enough to look right — 65 of 99 names came back "high-confidence" on units
    that are not the ones the data describes.
    """

    def guard(self, **summary):
        from emap import guardrails

        base = {"total": 99, "unmatched": 0, "fuzzy": 0}
        return guardrails.check_admin_level({**base, **summary}, "commune", "SNU2")

    def test_a_third_of_the_names_missing_raises_the_tier_question(self):
        found = self.guard(unmatched=30, fuzzy=3)
        self.assertEqual(len(found), 1)
        self.assertIn("cấp huyện", found[0]["why"])
        self.assertIn("SNU2", found[0]["why"])

    def test_a_clean_commune_join_says_nothing(self):
        self.assertEqual(self.guard(unmatched=1), [])

    def test_province_level_data_is_not_second_guessed(self):
        from emap import guardrails

        self.assertEqual(
            guardrails.check_admin_level({"total": 99, "unmatched": 30}, "province"), [])

    def test_a_tiny_table_is_not_judged_on_ratios(self):
        from emap import guardrails

        self.assertEqual(
            guardrails.check_admin_level({"total": 3, "unmatched": 2}, "commune"), [])


class TestASecondSpellingFromTheBoundaryFile(unittest.TestCase):
    """GADM's ``VARNAME_*`` was read into the profile and then never used.

    De-accenting already handles the easy half — "Ba Ria - Vung Tau" and
    "Bà Rịa - Vũng Tàu" normalise to one key without any alias. What an alias
    earns is the other half: a variant that is a *different name*, which no
    amount of normalising reaches.
    """

    FEATURES = [{"name": "Thành phố Hồ Chí Minh", "shape_id": 1,
                 "aliases": ["Sai Gon"]},
                {"name": "Hà Nội", "shape_id": 2}]

    def index(self):
        return matching.build_index(self.FEATURES, matching.VIETNAM)

    def test_the_alias_finds_the_unit(self):
        feature, score, method = matching.match_one("Sai Gon", self.index())
        self.assertEqual(feature["shape_id"], 1)
        self.assertEqual(score, 100.0)
        self.assertNotEqual(method, matching.FUZZY)

    def test_the_map_still_shows_the_name_not_the_alias(self):
        feature, _, _ = matching.match_one("Sai Gon", self.index())
        self.assertEqual(feature["name"], "Thành phố Hồ Chí Minh")

    def test_a_unit_without_an_alias_is_untouched(self):
        feature, _, method = matching.match_one("Hà Nội", self.index())
        self.assertEqual(feature["shape_id"], 2)
        self.assertEqual(method, matching.EXACT)

    def test_an_alias_never_creates_a_second_unit(self):
        """Both spellings lead to one feature, so a count of units is a count
        of units."""
        index = self.index()
        found = {f["shape_id"] for bucket in index.values() for f in bucket}
        self.assertEqual(found, {1, 2})
