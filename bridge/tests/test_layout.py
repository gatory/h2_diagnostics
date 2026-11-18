"""layout.py's tables must agree with each other (they describe the same topics)."""
from h2_diagnostics import layout


def test_every_live_topic_is_a_roles_first_choice():
    # LIVE_TOPICS and ROLES are two views of the same six topics. If one is edited
    # without the other, LiveSource subscribes to a topic that ingest() then drops
    # (or a role waits for a topic nobody subscribes to).
    first_choices = {topics[0] for topics in layout.ROLES.values()}
    assert first_choices == set(layout.LIVE_TOPICS)


def test_no_topic_fills_two_roles():
    # TOPIC_ROLE is built with a dict comprehension: a topic listed under two roles
    # would silently keep only the last one.
    all_topics = [t for topics in layout.ROLES.values() for t in topics]
    assert len(all_topics) == len(set(all_topics))
    assert len(layout.TOPIC_ROLE) == len(all_topics)
