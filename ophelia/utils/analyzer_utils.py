"""
Analyzer utilities module.

A collection of functions used for analyzing messages.
"""

import unicodedata

import numpy


def get_zalgo_percentile(percentile: float, text: str) -> float:
    """
    Get zalgo percentile for text.

    :param percentile: nth-percentile of diacritics per word
        (Default: 0.75)
    :param text: Text to analyze for zalgo
    :return: Zalgo percentile
    """

    word_scores = []
    for word in text.split():
        categories = [unicodedata.category(char) for char in word]
        diac_count = sum([categories.count(diac) for diac in ['Mn', 'Me']])

        if diac_count:
            score = diac_count / len(word)
            word_scores.append(score)

    return numpy.percentile(word_scores, percentile)
