import pytest

from comet.family_bootstrap import family_of, paired_family_difference


def outcomes(solved_by_task, seeds=(17, 29)):
    return {(task, seed): seed in solved for task, solved in solved_by_task.items() for seed in seeds}


def test_family_is_the_task_identifier_without_its_variant():
    assert family_of("396c5a2_3") == "396c5a2"


def test_identical_arms_have_zero_difference_and_a_degenerate_interval():
    arm = outcomes({"a_1": {17}, "a_2": set(), "b_1": {17, 29}, "b_2": {29}})
    result = paired_family_difference(arm, arm, draws=200, seed=1)
    assert result["difference"] == 0 and result["ci95"] == [0.0, 0.0]
    assert (result["families"], result["tasks"], result["seeds"]) == (2, 4, [17, 29])


def test_difference_averages_seeds_within_tasks_and_tasks_within_families():
    left = outcomes({"a_1": {17, 29}, "a_2": {17}, "b_1": set(), "b_2": set()})
    right = outcomes({"a_1": set(), "a_2": set(), "b_1": set(), "b_2": set()})
    result = paired_family_difference(left, right, draws=2000, seed=3)
    assert result["difference"] == pytest.approx((1.0 + 0.5) / 4)
    assert result["tasks_gained"] == ["a_1", "a_2"] and result["tasks_lost"] == []
    # Whole families are resampled, so the interval spans no family gaining to both draws gaining.
    assert result["ci95"] == [0.0, 0.75]


def test_resampling_families_is_wider_than_treating_their_tasks_as_independent():
    left = outcomes({f"{family}_{variant}": {17, 29} if family == "a" else set()
                     for family in "abcdefgh" for variant in (1, 2, 3)})
    right = outcomes({task: set() for task, _ in left})
    result = paired_family_difference(left, right, draws=4000, seed=5)
    assert result["difference"] == pytest.approx(1 / 8)
    low, high = result["ci95"]
    assert low == 0.0 and high >= 3 / 8


def test_unscored_or_unpaired_cells_are_rejected():
    left = outcomes({"a_1": {17}, "b_1": set()})
    with pytest.raises(ValueError, match="Unscored"):
        paired_family_difference({**left, ("a_1", 17): None}, left)
    with pytest.raises(ValueError, match="same tasks and seeds"):
        paired_family_difference(left, outcomes({"a_1": {17}}))
    with pytest.raises(ValueError, match="every seed"):
        paired_family_difference({("a_1", 17): True, ("b_1", 29): False}, {("a_1", 17): True, ("b_1", 29): False})


def test_tasks_weigh_equally_when_families_differ_in_size():
    left = outcomes({"a_1": {17, 29}, "a_2": {17, 29}, "a_3": {17, 29}, "b_1": set()})
    right = outcomes({task: set() for task, _ in left})
    result = paired_family_difference(left, right, draws=2000, seed=7)
    # Three of four tasks gain; a mean of family means would give one half.
    assert result["difference"] == pytest.approx(0.75)
    assert result["ci95"] == [0.0, 1.0]


def test_inputs_that_cannot_give_a_family_interval_are_rejected():
    one_family = outcomes({"a_1": {17}, "a_2": set()})
    with pytest.raises(ValueError, match="two families"):
        paired_family_difference(one_family, one_family)
    with pytest.raises(ValueError, match="two families"):
        paired_family_difference({}, {})
    two = outcomes({"a_1": {17}, "b_1": set()})
    with pytest.raises(ValueError, match="draws"):
        paired_family_difference(two, two, draws=10)
    with pytest.raises(ValueError, match="true or false"):
        paired_family_difference({**two, ("a_1", 17): 0.4}, two)


def test_tail_counts_say_how_often_resampling_reaches_zero_on_each_side():
    left = outcomes({"a_1": {17, 29}, "a_2": {17}, "b_1": set(), "b_2": set()})
    right = outcomes({task: set() for task, _ in left})
    gain = paired_family_difference(left, right, draws=2000, seed=3)
    # Only the draw of family b twice gives zero; no draw is negative.
    assert 0 < gain["draws_at_or_below_zero"] < 2000 * 0.4
    assert gain["draws_at_or_above_zero"] == 2000
    loss = paired_family_difference(right, left, draws=2000, seed=3)
    assert loss["draws_at_or_above_zero"] == gain["draws_at_or_below_zero"]
    assert loss["draws_at_or_below_zero"] == 2000
