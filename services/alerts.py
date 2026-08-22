"""Backward-compatible alert entry point.

The actual persistence, image linking and notification logic lives in
services.abnormal so abnormal conditions remain queryable after the request ends.
"""

from services.abnormal import evaluate_vital


def check_and_alert(elder, vital, lang="zh"):
    return evaluate_vital(elder, vital, lang=lang)
