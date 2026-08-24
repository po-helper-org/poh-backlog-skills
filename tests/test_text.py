from poh_backlog.text import ru_plural


def test_one_form_for_count_ending_in_one():
    assert ru_plural(1, "слово", "слова", "слов") == "слово"


def test_few_form_for_count_two_to_four():
    assert ru_plural(2, "слово", "слова", "слов") == "слова"


def test_many_form_for_count_five_and_up():
    assert ru_plural(5, "слово", "слова", "слов") == "слов"


def test_many_form_for_teen_eleven():
    assert ru_plural(11, "слово", "слова", "слов") == "слов"


def test_one_form_for_twenty_one():
    assert ru_plural(21, "слово", "слова", "слов") == "слово"


def test_many_form_for_hundred_eleven():
    assert ru_plural(111, "слово", "слова", "слов") == "слов"


def test_many_form_for_zero():
    assert ru_plural(0, "слово", "слова", "слов") == "слов"
