"""relsend: the only process that sends (its own OS user, its own credentials in /etc/relcore/relsend.env).

It takes signed decisions from spool/approved, verifies them, and drains the outbox one message at a time with
every check before every message. Any doubt about whether a provider accepted a message sets the row to
`unknown`, halts the worker and alerts the owner; nothing is ever re-sent automatically.
"""
