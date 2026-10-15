from pisorentbot.crime import crime_score


def test_crime_score_is_normalized_and_capped():
    assert crime_score(0, 250) == 0
    assert crime_score(125, 250) == 50
    assert crime_score(500, 250) == 100
