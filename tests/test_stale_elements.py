import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium.common.exceptions import StaleElementReferenceException

from li_selectors import visible


class Fake:
    def __init__(self, shown=True, stale=False):
        self.shown, self.stale = shown, stale

    def is_displayed(self):
        if self.stale:
            raise StaleElementReferenceException("stale element reference")
        return self.shown


def test_visible_keeps_displayed_elements_only():
    a, b = Fake(True), Fake(False)
    assert visible([a, b]) == [a]


def test_visible_skips_elements_that_went_stale_instead_of_crashing():
    """Regression: LinkedIn redraws the page while the bot checks a button; that used to end the whole run."""
    ok = Fake(True)
    assert visible([Fake(stale=True), ok, Fake(stale=True)]) == [ok]
    assert visible([]) == []
