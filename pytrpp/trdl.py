import logging
import re

from pathlib import Path
from concurrent.futures import as_completed, Future
from requests import session
from requests_futures.sessions import FuturesSession
import json
import asyncio
from datetime import datetime, timezone
import logging

try:
    from api import TradeRepublicError
except ImportError:
    from .api import TradeRepublicError


def get_timestamp(ts: str) -> datetime:
    """Convert string timestamp to datetime object."""
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return datetime.fromisoformat(ts[:19])


class Timeline:
    def __init__(self, tr, since_timestamp=None, max_workers=8, logger=None):
        self.tr = tr
        if logger is None:
            self.log = logging.getLogger(__name__)
        else:
            self.log = logger
        self.errors = 0
        self.received_detail = 0
        self.requested_detail = 0
        self.num_timeline_details = 0
        self.events = []
        self.num_timelines = 0
        self.timeline_events = {}
        self.timeline_events_iter = None
        self.done = False
        self.since_timestamp = since_timestamp if since_timestamp is not None else datetime.fromtimestamp(0, timezone.utc)

        requests_session = session()
        if self.tr._weblogin:
            requests_session.headers = self.tr._default_headers_web
        else:
            requests_session.headers = self.tr._default_headers
        self.session = FuturesSession(max_workers=max_workers, session=requests_session)

    async def get_next_timeline_transactions(self, response=None):
        '''
        Get timelines transactions and save time in list timelines.
        Extract timeline transactions events and save them in list timeline_events
        '''

        if response is None:
            # empty response / first timeline
            self.log.info('Awaiting #1  timeline transactions')
            self.num_timelines = 0
            await self.tr.timeline_transactions()
        else:
            self.num_timelines += 1
            # print(json.dumps(response))
            for event in response['items']:
                if get_timestamp(event['timestamp']) >= self.since_timestamp:
                    event['source'] = "timelineTransaction"
                    self.timeline_events[event['id']] = event
                    self.num_timeline_details += 1

            after = response['cursors'].get('after')
            timestamp = get_timestamp(response['items'][-1]['timestamp'])
            if after is None or timestamp < self.since_timestamp:
                # last timeline is reached
                await self.get_next_timeline_activity_log()
            else:
                self.log.info(
                    f'Received #{self.num_timelines:<2} timeline transactions, awaiting #{self.num_timelines+1:<2} timeline transactions'
                )
                await self.tr.timeline_transactions(after)

    async def get_next_timeline_activity_log(self, response=None):
        '''
        Get timelines acvtivity log and save time in list timelines.
        Extract timeline acvtivity log events and save them in list timeline_events
        '''

        if response is None:
            # empty response / first timeline
            self.log.info('Awaiting #1  timeline activity log')
            self.num_timelines = 0
            await self.tr.timeline_activity_log()
        else:
            timestamp = get_timestamp(response['items'][-1]['timestamp'])
            self.num_timelines += 1
            # print(json.dumps(response))
            for event in response['items']:
                if event['id'] not in self.timeline_events:
                    if get_timestamp(event['timestamp']) >= self.since_timestamp:
                        event['source'] = "timelineActivity"
                        self.timeline_events[event['id']] = event
                        self.num_timeline_details += 1

            after = response['cursors'].get('after')
            if after is None:
                # last timeline is reached
                self.log.info(f'Received #{self.num_timelines:<2} (last) timeline activity log')
                self.timeline_events_iter = iter(self.timeline_events.values())
                await self._get_timeline_details(5)
            elif timestamp < self.since_timestamp:
                self.log.info(f'Received #{self.num_timelines+1:<2} timeline activity log')
                self.log.info('Reached last relevant timeline activity log')
                self.timeline_events_iter = iter(self.timeline_events.values())
                await self._get_timeline_details(5)
            else:
                self.log.info(
                    f'Received #{self.num_timelines:<2} timeline activity log, awaiting #{self.num_timelines+1:<2} timeline activity log'
                )
                await self.tr.timeline_activity_log(after)

    async def _get_timeline_details(self, num_torequest):
        '''
        request timeline details
        '''
        while num_torequest > 0:

            try:
                event = next(self.timeline_events_iter)
            except StopIteration:
                self.log.info('All timeline details requested')
                if self.requested_detail == 0:
                    self.done = True
                return False

            action = event.get('action')
            # icon = event.get('icon')
            msg = ''
            if get_timestamp(event['timestamp']) < self.since_timestamp:
                msg += 'Skip: too old'
            elif action is None:
                if event.get('actionLabel') is None:
                    msg += 'Skip: no action'
            elif action.get('type') != 'timelineDetail':
                msg += f"Skip: action type unmatched ({action['type']})"
            elif action.get('payload') != event['id']:
                msg += f"Skip: payload unmatched ({action['payload']})"

            if msg != '':
                self.log.debug(f"{msg} {event['title']}: {event.get('body')} {json.dumps(event)}")
                self.num_timeline_details -= 1
                continue

            self.events.append(event)
            num_torequest -= 1
            self.requested_detail += 1
            await self.tr.timeline_detail_v2(event['id'])

    async def timelineDetail(self, response, dl):
        '''
        process timeline response and request timelines
        '''
        self.received_detail += 1
        event = self.timeline_events[response['id']]
        event['details'] = response

        # when all requested timeline events are received request 5 new
        if self.received_detail == self.requested_detail:
            remaining = len(self.timeline_events)
            if remaining == 0:
                self.done = True
            elif remaining < 5:
                await self._get_timeline_details(remaining)
            else:
                await self._get_timeline_details(5)

        max_details_digits = len(str(self.num_timeline_details))
        self.log.info(
            f"{self.received_detail:>{max_details_digits}}/{self.num_timeline_details}: {self.get_event_info(event)}"
        )

        if self.received_detail == self.num_timeline_details:
            self.log.info('Received all details')
            self.done = True

    @staticmethod
    def get_event_info(event):
        return f"{event.get('eventType', '')}: {event.get('title', '')} -- {event.get('subtitle', '')}"

    async def dl_loop(self):
        await self.get_next_timeline_transactions()

        while not self.done:
            try:
                _subscription_id, subscription, response = await self.tr.recv()
            except TradeRepublicError as e:
                self.log.error(str(e))
                self.received_detail += 1
                self.errors += 1
                continue

            if subscription['type'] == 'timelineTransactions':
                await self.get_next_timeline_transactions(response)
            elif subscription['type'] == 'timelineActivityLog':
                await self.get_next_timeline_activity_log(response)
            elif subscription['type'] == 'timelineDetailV2':
                await self.timelineDetail(response, self)
            else:
                self.log.warning(f"unmatched subscription of type '{subscription['type']}'")

    def get_events(self):
        if not self.done:
            asyncio.get_event_loop().run_until_complete(self.dl_loop())
        return self.events


class Downloader:
    """Download multiple files asynchronously"""

    def __init__(self, headers: dict[str, str|bytes], max_workers=8):
        self.futures: list[Future] = []
        self.errors: int = 0
        requests_session = session()
        requests_session.headers = headers
        self.session = FuturesSession(max_workers=max_workers, session=requests_session)

    def dl(self, url: str, filepath: Path|str, redownload: bool = False):
        filepath = Path(filepath)
        if not filepath.exists() or redownload:
            future = self.session.get(url)
            future.filepath = filepath
            self.futures.append(future)

    def wait(self):
        for future in as_completed(self.futures):
            filepath: Path = future.filepath

            try:
                result = future.result()
            except Exception as e:
                self.errors += 1
            else:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(result.content)
