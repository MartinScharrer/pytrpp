#!/usr/bin/env python
__VERSION__ = '0.3.0'

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import json
import string
import time
import logging
import coloredlogs

try:
    from trdl import Timeline, Downloader, get_timestamp
    from api import TradeRepublicApi
    from conv import Converter
except ImportError:
    from .trdl import Timeline, Downloader, get_timestamp
    from .api import TradeRepublicApi
    from .conv import Converter

get_logger = logging.getLogger


class Credentials:
    def __init__(self, phone_no=None, pin=None, credentials_file=None, store_credentials=0):
        self.phone_no = phone_no
        self.pin = pin
        self.credentials_file = credentials_file
        self.store_credentials = store_credentials

        # Load from file if not given
        if not self.phone_no or not self.pin:
            file_content_used = False
            phone_no_file, pin_file = self.load()
            if not self.phone_no:
                self.phone_no = phone_no_file
            if not self.pin:
                self.pin = pin_file

        # If not in file as well
        if not self.phone_no or not self.pin:
            self.input()

        if store_credentials:
            self.store()

    def input(self):
        if not self.phone_no:
            self.phone_no = input("Please enter phone number (international format): ")
        if not self.pin:
            self.pin = input("Please enter PIN: ")

    def load(self) -> tuple[str|None, str|None]:
        if not self.credentials_file:
            return None, None
        try:
            lines: list[str|None] = Path(self.credentials_file).read_text(encoding='utf8').splitlines(keepends=False)
            lines.extend((None, None))
            return lines[0], lines[1]
        except FileNotFoundError:
            return None, None

    def store(self):
        if self.credentials_file and self.store_credentials:
            phone_no = self.phone_no if self.phone_no else ''
            pin = self.pin if self.pin and self.store_credentials >= 2 else ''
            p = Path(self.credentials_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f'{phone_no}\n{pin}\n', encoding='utf8')


class PyTrPP:
    Downloader = Downloader
    Converter = Converter
    Credentials = Credentials

    COOKIE_FILE = '.pytrpp/cookies.txt'
    CREDENTIALS_FILE = '.pytrpp/credentials.txt'
    EVENTS_FILE = 'events.json'
    PAYMENTS_FILE = 'payments.csv'
    ORDERS_FILE = 'orders.csv'

    def __init__(self, phone_no, pin, credentials_file=None, cookies_file=None,
                 docs_dir=None, events_file=None, payments_file=None, orders_file=None,
                 locale='de', since=None, workers=8, logger=None, store_credentials=0):
        credentials = self.Credentials(phone_no, pin, credentials_file, store_credentials)
        self.phone_no = credentials.phone_no
        self.pin = credentials.pin
        self.credentials_file = credentials.credentials_file
        self.cookies_file = cookies_file
        self.save_cookies = bool(cookies_file)
        self.docs_dir = docs_dir
        self.events_file = events_file
        self.payments_file = payments_file
        self.orders_file = orders_file
        self.locale = locale
        self.since = since
        self.workers = workers
        self.tr: TradeRepublicApi|None = None
        self.events: list[dict] = []
        self.logger = logger if logger is not None else self.get_logger()

    def process(self):
        self.login()

        tl = Timeline(
            tr=self.tr,
            since_timestamp=self.since,
            max_workers=self.workers,
            logger=self.logger,
        )
        self.events = tl.get_events()

        if self.docs_dir:
            dl = self.Downloader(
                headers=self.tr.get_default_headers(),
                max_workers=self.workers,
            )
            self.process_dl(self.events, self.docs_dir, dl.dl)
            dl.wait()

        if self.payments_file or self.orders_file:
            self.Converter().convert(self.events, self.payments_file, self.orders_file)

        if self.events_file:
            with open(self.events_file, 'w') as fh:
                json.dump(self.events, fh, indent=2)

    def input(self, request_time, countdown):
        print('Enter the code you received to your mobile app as a notification.')
        print(f'Enter nothing if you want to receive the (same) code as SMS. (Countdown: {countdown})')
        code = input('Code: ')
        if code == '':
            countdown = countdown - (time.time() - request_time)
            for remaining in range(int(countdown)):
                print(f'Need to wait {int(countdown - remaining)} seconds before requesting SMS...', end='\r')
                time.sleep(1)
            print()
            self.tr.resend_weblogin()
            code = input('SMS requested. Enter the confirmation code:')
        return code

    def login(self):
        '''
        If web is true, use web login method as else simulate app login.
        Check if credentials file exists else create it.
        If no parameters are set but are needed then ask for input
        '''
        log = self.logger
        self.tr = TradeRepublicApi(phone_no=self.phone_no, pin=self.pin, locale=self.locale,
                                   save_cookies=self.save_cookies, cookies_file=self.cookies_file,
                                   credentials_file=self.credentials_file)

        # Use same login as app.traderepublic.com
        if self.tr.resume_websession():
            log.info('Web session resumed')
        else:
            try:
                countdown = self.tr.inititate_weblogin()
                request_time = time.time()
                code = self.input(request_time, countdown)
                self.tr.complete_weblogin(code)
            except ValueError as e:
                try:
                    for err in json.loads(str(e)):
                        match err:
                            case {'errorCode': 'NUMBER_INVALID', 'errorMessage': 'phoneNumber'}:
                                log.error("Phone number invalid")
                            case {'errorCode': 'INVALID_VALUE', 'errorMessage': 'pin'}:
                                log.error("PIN number invalid")
                            case {"errorCode": "AUTHENTICATION_ERROR"}:
                                log.error("Authentication error")
                            case {"errorCode":"VALIDATION_CODE_INVALID"}:
                                log.error("Validation code invalid")
                            case {"errorCode": "TOO_MANY_REQUESTS", "meta": {"_meta_type": "RetryMeta", "nextAttemptInSeconds": seconds, "nextAttemptTimestamp": _}}:
                                ts = datetime.now() + timedelta(seconds=seconds)  # Used instead of 'nextAttemptTimestamp' to use local time zone
                                log.error(f"Too many requests. Try again in {seconds} seconds at {ts.strftime('%Y-%m-%d %H:%M:%S %Z').rstrip()}.")
                    raise ConnectionError("Could not connect to Trade Republic server.")
                except (TypeError, KeyError):
                    log.error("Invalid credentials or validation code.")
                    raise ConnectionError("Could not connect to Trade Republic server. Please check credentials and try again.")

        log.info('Logged in')

    @staticmethod
    def filepath(event: dict, doc: dict, dt: datetime, extension: str) -> Path:
        """Return target filepath for given document"""
        return Path(string.capwords(event['eventType'], '_')) / f"{dt:%Y-%m-%d} - {doc['title']} - {doc['id']}.{extension}"

    def process_dl(self, events: dict, base_dir: Path, dl: callable):
        base_dir = Path(base_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Downloading file into directory '{base_dir}'")
        files = []
        for event in events:
            if 'details' in event:
                for section in event['details']['sections']:
                    if section['type'] == 'documents':
                        for doc in section['data']:
                            try:
                                dt = datetime.strptime(doc['detail'], '%d.%m.%Y')
                            except (ValueError, KeyError):
                                dt = get_timestamp(event['timestamp'])
                            doc_url = doc['action']['payload']
                            try:
                                extension = doc_url[:doc_url.index('?')]
                                extension = extension[extension.rindex('.') + 1:]
                            except ValueError:
                                extension = 'pdf'
                            filepath = self.filepath(event, doc, dt, extension)
                            files.append((doc_url, filepath))
        num = len(files)
        skipped = 0
        for n,(doc_url, filepath) in enumerate(reversed(files), start=1):
            fullpath = base_dir / filepath
            if fullpath.exists():
                skipped += 1
                self.logger.debug(f"Skipping file {n}/{num}: '{filepath}'")
            else:
                self.logger.info(f"Downloading file {n}/{num}: '{filepath}'")
                dl(doc_url, fullpath)
        ndl = num - skipped
        if ndl:
            self.logger.info(f"Downloaded {ndl} files.")
        if skipped:
            self.logger.info(f"Skipped {skipped} files as they were already present.")

    @classmethod
    def main(cls, argv=None):
        parser = cls.get_parser()
        args = cls.parse(parser, argv)
        if args.version:
            parser.exit(0, f'pytrpp v{__VERSION__} -- Download TradeRepublic files and export data to Portfolio Performance')
        try:
            cls(
                phone_no=args.phone_no,
                pin=args.pin,
                credentials_file=args.credentials_file,
                cookies_file=args.cookies_file,
                docs_dir=args.docs_dir,
                events_file=args.events_file,
                payments_file=args.payments_file,
                orders_file=args.orders_file,
                locale=args.locale,
                since=args.since,
                workers=args.workers,
                store_credentials=args.store_credentials,
            ).process()
        except ValueError as e:
            parser.error(str(e))
        except ConnectionError as e:
            parser.exit(1, str(e))

    @classmethod
    def parse(cls, parser=None, argv=None):
        if parser is None:
            parser = cls.get_parser()
        args = parser.parse_args(argv)

        if args.dir:
            args.dir = Path(args.dir)
            if not args.docs_dir:
                args.docs_dir = args.dir
            if args.cookies_file is None:
                args.cookies_file = args.dir / cls.COOKIE_FILE
            if args.credentials_file is None:
                args.credentials_file = args.dir / cls.CREDENTIALS_FILE
            if args.events_file is None:
                args.events_file = args.dir / cls.EVENTS_FILE
            if args.payments_file is None:
                args.payments_file = args.dir / cls.PAYMENTS_FILE
            if args.orders_file is None:
                args.orders_file = args.dir / cls.ORDERS_FILE
        elif not any((args.docs_dir, args.events_file, args.payments_file, args.orders_file)):
            parser.error('No output target selected. Try adding "-D <OutputDirectory>".')

        return args

    @staticmethod
    def get_parser():
        def formatter(prog):
            return argparse.HelpFormatter(prog, max_help_position=25)

        parser = argparse.ArgumentParser(
            formatter_class=formatter,
            description='Use "%(prog)s command_name --help" to get detailed help to a specific command',
        )

        parser.add_argument(
            '-v',
            '--verbosity',
            help='Set verbosity level (default: info)',
            choices=['warning', 'info', 'debug'],
            default='info',
        )
        parser.add_argument('-V', '--version', help='Print version information and quit', action='store_true')
        parser.add_argument('-n', '--phone_no', help='TradeRepublic phone number (international format)')
        parser.add_argument('-p', '--pin', help='TradeRepublic pin')

        parser.add_argument('-l', '--locale', help='Locale setting (e.g. "en" for English, "de" for German)',
                            default='de', type=str)

        parser.add_argument('-D', '--dir', type=Path, default=None,
                            help='Main directory to use. Special path can be set using the following options.')
        parser.add_argument('-K', '--cookies-file', help='Cookies file')
        parser.add_argument('-C', '--credentials-file', help='Credentials file')
        parser.add_argument('-S', '--store-credentials', action='count', default=0,
                            help='Store credentials in file. If used once the phone number will be stored. Use twice to also store the PIN.', )
        parser.add_argument('-E', '--events-file', help='Events file to store')
        parser.add_argument('-P', '--payments-file', help='Payments file to store')
        parser.add_argument('-O', '--orders-file', help='Orders file to store')
        parser.add_argument('-F', '--docs-dir', help='Directory to download files to')

        since_group = parser \
            .add_argument_group('Date Range', 'Control date range to include (mutually exclusive):') \
            .add_mutually_exclusive_group()
        since_group.add_argument(
            '-d', '--last-days', help='Number of last days to include', metavar='DAYS', dest='since',
            type=lambda s: datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                           - timedelta(days=int(s) - 1)
        )

        since_group.add_argument('-s', '--since', help='Include only entry since this date', metavar='DATE',
                                 dest='since',
                                 type=lambda s: datetime.fromisoformat(s).astimezone(timezone.utc),
                                 )
        since_group.add_argument('-r', '--since-ref',
                                 help='Include only entry newer than the modified date of this file',
                                 metavar='FILE', dest='since',
                                 type=lambda s: datetime.fromtimestamp(Path(s).stat().st_mtime, timezone.utc))

        parser.add_argument(
            '--workers', help='Number of workers for parallel downloading', metavar='WORKERS', default=8, type=int
        )

        return parser

    @staticmethod
    def get_logger(name=__name__, log_level=None):
        '''
        Colored logging

        :param name: logger name (use __name__ variable)
        :param log_level:
        :return: Logger
        '''
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


def main(argv=None):
    PyTrPP.main(argv)


if __name__ == '__main__':
    main()
