from datetime import datetime
from zoneinfo import ZoneInfo
from app import fetch_matches,attach_odds,archive_finished
IST=ZoneInfo('Europe/Istanbul'); day=datetime.now(IST).date()
print('matches',fetch_matches(day)); print('odds',attach_odds(day)); print('archive',archive_finished(day))
