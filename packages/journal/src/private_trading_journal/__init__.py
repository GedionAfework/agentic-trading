"""Trade journal and analytics. Paper cohort is never silently merged with backtest/manual."""

from private_trading_journal.service import create_paper_journal_entry, list_journal_entries

__version__ = "0.1.0"

__all__ = ["create_paper_journal_entry", "list_journal_entries", "__version__"]
