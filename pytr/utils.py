#!/usr/bin/env python3

import coloredlogs
import json
import logging
import requests
from datetime import datetime
from locale import getdefaultlocale
from packaging import version
from pathlib import Path
from string import capwords
log_level = None


def timestamp(ts: str) -> datetime:
    """Convert string timestamp to datetime object."""
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return datetime.fromisoformat(ts[:19])


def get_logger(name=__name__, verbosity=None):
    '''
    Colored logging

    :param name: logger name (use __name__ variable)
    :param verbosity:
    :return: Logger
    '''
    global log_level
    if verbosity is not None:
        if log_level is None:
            log_level = verbosity
        else:
            raise RuntimeError('Verbosity has already been set.')

    shortname = name.replace('pytr.', '')
    logger = logging.getLogger(shortname)

    # no logging of libs
    logger.propagate = False

    if log_level == 'debug':
        fmt = '%(asctime)s %(name)-9s %(levelname)-8s %(message)s'
        datefmt = '%Y-%m-%d %H:%M:%S%z'
    else:
        fmt = '%(asctime)s %(message)s'
        datefmt = '%H:%M:%S'

    fs = {
        'asctime': {'color': 'green'},
        'hostname': {'color': 'magenta'},
        'levelname': {'color': 'red', 'bold': True},
        'name': {'color': 'magenta'},
        'programname': {'color': 'cyan'},
        'username': {'color': 'yellow'},
    }

    ls = {
        'critical': {'color': 'red', 'bold': True},
        'debug': {'color': 'green'},
        'error': {'color': 'red'},
        'info': {},
        'notice': {'color': 'magenta'},
        'spam': {'color': 'green', 'faint': True},
        'success': {'color': 'green', 'bold': True},
        'verbose': {'color': 'blue'},
        'warning': {'color': 'yellow'},
    }

    coloredlogs.install(level=log_level, logger=logger, fmt=fmt, datefmt=datefmt, level_styles=ls, field_styles=fs)

    return logger


class Timeline:
    def __init__(self, tr):
        self.tr = tr
        self.log = get_logger(__name__)
        self.received_detail = 0
        self.requested_detail = 0
        self.num_timeline_details = 0
        self.events = []
        self.num_timelines = 0
        self.timeline_events = {}
        self.timeline_events_iter = None

    async def get_next_timeline_transactions(self, response=None, max_age_timestamp=0):
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
            timestamp = response['items'][-1]['timestamp']
            self.num_timelines += 1
            # print(json.dumps(response))
            self.num_timeline_details += len(response['items'])
            for event in response['items']:
                event['source'] = "timelineTransaction"
                self.timeline_events[event['id']] = event

            after = response['cursors'].get('after')
            if after is None:
                # last timeline is reached
                await self.get_next_timeline_activity_log()
            else:
                self.log.info(
                    f'Received #{self.num_timelines:<2} timeline transactions, awaiting #{self.num_timelines+1:<2} timeline transactions'
                )
                await self.tr.timeline_transactions(after)

    async def get_next_timeline_activity_log(self, response=None, max_age_timestamp=0):
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
            timestamp = response['items'][-1]['timestamp']
            self.num_timelines += 1
            # print(json.dumps(response))
            self.num_timeline_details += len(response['items'])
            for event in response['items']:
                if event['id'] not in self.timeline_events:
                    event['source'] = "timelineActivity"
                    self.timeline_events[event['id']] = event

            after = response['cursors'].get('after')
            if after is None:
                # last timeline is reached
                self.log.info(f'Received #{self.num_timelines:<2} (last) timeline activity log')
                self.timeline_events_iter = iter(self.timeline_events.values())
                await self._get_timeline_details(5)
            elif max_age_timestamp != 0 and timestamp < max_age_timestamp:
                self.log.info(f'Received #{self.num_timelines+1:<2} timeline activity log')
                self.log.info('Reached last relevant timeline activity log')
                self.timeline_events_iter = iter(self.timeline_events.values())
                await self._get_timeline_details(5, max_age_timestamp=max_age_timestamp)
            else:
                self.log.info(
                    f'Received #{self.num_timelines:<2} timeline activity log, awaiting #{self.num_timelines+1:<2} timeline activity log'
                )
                await self.tr.timeline_activity_log(after)

    async def _get_timeline_details(self, num_torequest, max_age_timestamp=0):
        '''
        request timeline details
        '''
        while num_torequest > 0:

            try:
                event = next(self.timeline_events_iter)
            except StopIteration:
                self.log.info('All timeline details requested')
                return False

            action = event.get('action')
            # icon = event.get('icon')
            msg = ''
            if max_age_timestamp != 0 and event['timestamp'] > max_age_timestamp:
                msg += 'Skip: too old'

            elif action is None:
                if event.get('actionLabel') is None:
                    msg += 'Skip: no action'
            elif action.get('type') != 'timelineDetail':
                msg += f"Skip: action type unmatched ({action['type']})"
            elif action.get('payload') != event['id']:
                msg += f"Skip: payload unmatched ({action['payload']})"

            self.events.append(event)
            if msg != '':
                self.log.debug(f"{msg} {event['title']}: {event.get('body')} {json.dumps(event)}")
                self.num_timeline_details -= 1
                continue

            num_torequest -= 1
            self.requested_detail += 1
            await self.tr.timeline_detail_v2(event['id'])

    async def timelineDetail(self, response, dl, max_age_timestamp=0):
        '''
        process timeline response and request timelines
        '''

        self.received_detail += 1
        event = self.timeline_events[response['id']]
        event['details'] = response

        dt = timestamp(event['timestamp'])

        # when all requested timeline events are received request 5 new
        if self.received_detail == self.requested_detail:
            remaining = len(self.timeline_events)
            if remaining < 5:
                await self._get_timeline_details(remaining)
            else:
                await self._get_timeline_details(5)

        max_details_digits = len(str(self.num_timeline_details))
        self.log.info(
            f"{self.received_detail:>{max_details_digits}}/{self.num_timeline_details}: "
            + f"{event.get('title', '')} -- {event.get('subtitle', '')}"
        )

        for section in response['sections']:
            if section['type'] == 'documents':
                for doc in section['data']:
                    doc_url = doc['action']['payload']
                    try:
                        url = doc_url.split('?')[0]
                        extension = url[url.rindex('.')-1:]
                    except (IndexError, ValueError):
                        extension = ''
                    filepath = f"{doc['title']} - {dt:%Y-%m-%d} - {doc['id']}{extension}"
                    doc['action']['localpath'] = str(filepath)
                    dl.dl_doc(doc_url=doc_url, filepath=filepath, subfolder=capwords(event['eventType'], '_'))

        if self.received_detail == self.num_timeline_details:
            self.log.info('Received all details')
            dl.output_path.mkdir(parents=True, exist_ok=True)
            with open(dl.output_path / 'events.json', 'w', encoding='utf-8') as f:
                json.dump(self.events, f, ensure_ascii=False, indent=2)

            dl.work_responses()
